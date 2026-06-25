"""Stage 8: Quality Gate Decision Logic."""

from typing import List, Optional

from backend.config import settings, PipelineConfig
from backend.models import EvaluationResult
from backend.observability import instrument_stage
import logfire


@instrument_stage(PipelineConfig.STAGE_QUALITY_GATE)
async def quality_gate_decision(
    average_score: float,
    evaluations: List[EvaluationResult],
    accuracy_score: int,
    current_iteration: int,
    errors: List[str],
    corrections: List[str]
) -> dict:
    """
    Decide whether to return answer or iterate.
    
    Args:
        average_score: Average quality score from evaluators
        evaluations: Individual evaluation results
        accuracy_score: Technical accuracy score
        current_iteration: Current iteration number
        errors: List of identified errors
        corrections: List of suggested corrections
        
    Returns:
        dict with 'should_iterate', 'feedback', 'reason'
    """
    
    logfire.info(
        "Quality gate decision",
        average_score=average_score,
        accuracy_score=accuracy_score,
        current_iteration=current_iteration,
        max_iterations=settings.max_iterations
    )
    
    should_iterate = False
    reason = ""
    feedback: Optional[str] = None
    
    # Check if we've hit max iterations
    if current_iteration >= settings.max_iterations:
        reason = f"Maximum iterations ({settings.max_iterations}) reached"
        logfire.info(reason)
        return {
            "should_iterate": False,
            "feedback": None,
            "reason": reason
        }
    
    # Check quality threshold
    if average_score < settings.quality_threshold:
        should_iterate = True
        reason = f"Quality score {average_score:.1f} below threshold {settings.quality_threshold}"
        
        # Merge feedback from evaluators
        feedback_parts = [
            f"Quality score: {average_score:.1f}/100 (threshold: {settings.quality_threshold})"
        ]
        
        for eval_result in evaluations:
            if eval_result.score < settings.quality_threshold:
                feedback_parts.append(f"\n{eval_result.model} feedback: {eval_result.feedback}")
        
        feedback = "\n".join(feedback_parts)
    
    # NOTE: Accuracy threshold check DISABLED
    # Empirical testing showed accuracy scoring is unreliable:
    # - Score dropped from 75 to 25 after iteration (with 96% verification!)
    # - High variance even with temperature=0
    # - Causes unnecessary iterations that degrade quality
    # - First iteration is usually the best answer
    # We keep accuracy checking for monitoring/logging, but don't gate on it
    
    # elif accuracy_score < settings.accuracy_threshold:
    #     should_iterate = True
    #     reason = f"Accuracy score {accuracy_score} below threshold {settings.accuracy_threshold}"
    #     
    #     feedback_parts = [
    #         f"Accuracy score: {accuracy_score}/100 (threshold: {settings.accuracy_threshold})"
    #     ]
    #     
    #     if errors:
    #         feedback_parts.append("\nIdentified errors:")
    #         feedback_parts.extend([f"- {error}" for error in errors[:3]])
    #     
    #     if corrections:
    #         feedback_parts.append("\nSuggested corrections:")
    #         feedback_parts.extend([f"- {correction}" for correction in corrections[:3]])
    #     
    #     feedback = "\n".join(feedback_parts)
    
    # Check for significant disagreement between evaluators
    elif len(evaluations) >= 2:
        score_diff = abs(evaluations[0].score - evaluations[1].score)
        if score_diff > settings.agreement_threshold:
            should_iterate = True
            reason = f"Evaluator disagreement too high: {score_diff} points"
            feedback = f"Evaluators disagree significantly. {evaluations[0].model} says: {evaluations[0].feedback}. {evaluations[1].model} says: {evaluations[1].feedback}"
    
    # All checks passed
    else:
        reason = f"Quality score {average_score:.1f} and accuracy {accuracy_score} meet thresholds"
    
    logfire.info(
        "Quality gate result",
        should_iterate=should_iterate,
        reason=reason,
        has_feedback=feedback is not None
    )
    
    return {
        "should_iterate": should_iterate,
        "feedback": feedback,
        "reason": reason
    }

