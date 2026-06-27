# Deploying a Node.js App on Render
Source: https://render.com/docs/deploy-node-express-app

## Overview
Render supports Node.js web services, background workers, and static sites.
Node.js apps deploy using Render's native Node.js buildpack or a custom Dockerfile.
Render auto-detects Node.js projects via the presence of a package.json file.

## Quick Start: Deploy Node.js via Dashboard
1. Push your Node.js project to GitHub or GitLab.
2. In the Render Dashboard, click **New → Web Service** and connect your repo.
3. Render auto-detects Node.js via package.json.
4. Set the **Build Command** (e.g. `npm install` or `npm run build`).
5. Set the **Start Command** (e.g. `node index.js` or `npm start`).
6. Choose an instance type and click **Deploy**.

## render.yaml (Infrastructure as Code)
```yaml
services:
  - type: web
    name: my-node-app
    runtime: node
    buildCommand: npm install
    startCommand: node index.js
    plan: starter
    envVars:
      - key: NODE_ENV
        value: production
      - key: PORT
        sync: false
```

## PORT Environment Variable (CRITICAL)
Render automatically sets the `PORT` environment variable. Your Node.js app **must**
listen on `process.env.PORT`:

```javascript
const port = process.env.PORT || 3000;
app.listen(port, () => {
  console.log(`Server running on port ${port}`);
});
```

## Node.js Version
Specify your Node.js version using one of these methods:
- **package.json engines field** (recommended):
  ```json
  "engines": { "node": "20.x" }
  ```
- **.node-version file** in the project root: `20.x`
- **.nvmrc file** in the project root: `20`

## Build and Start Commands
Common patterns:
- **Simple app**: Build: `npm install`, Start: `node server.js`
- **TypeScript**: Build: `npm install && npm run build`, Start: `node dist/index.js`
- **npm scripts**: Build: `npm install`, Start: `npm start`
- **Production install**: Build: `npm ci`, Start: `node index.js`

## Health Checks
Render performs HTTP health checks on your service. Your app must respond with a 2xx
status on the configured health check path (default: `/`). Configure the path in
Dashboard → Settings → Health & Alerts.

## Environment Variables
Set environment variables in the Dashboard under **Environment** or in render.yaml:
```yaml
envVars:
  - key: DATABASE_URL
    fromDatabase:
      name: my-postgres-db
      property: connectionString
  - key: SECRET_KEY
    generateValue: true
```

## Connecting to a Database
For Render Postgres, use the `DATABASE_URL` environment variable:
```javascript
const { Pool } = require('pg');
const pool = new Pool({ connectionString: process.env.DATABASE_URL });
```

## Static Sites vs Web Services for JavaScript Apps
- **Render Static Sites** (free): Use for purely static output — plain HTML/CSS/JS,
  Vite builds, Create React App, etc. No server-side rendering.
- **Render Web Services**: Use for server-side rendering — Next.js App Router, Remix,
  Express APIs, Nuxt.js, etc. Requires a running Node.js process.

## Next.js Deployment
For Next.js with App Router (SSR):
```yaml
services:
  - type: web
    name: my-nextjs-app
    runtime: node
    buildCommand: npm install && npm run build
    startCommand: npm start
    envVars:
      - key: NODE_ENV
        value: production
```

For Next.js static export (`output: 'export'` in next.config.js):
```yaml
services:
  - type: static
    name: my-nextjs-static
    buildCommand: npm install && npm run build
    staticPublishPath: ./out
```

## Persistent Disk
Mount a persistent disk for stateful storage (SQLite, uploaded files):
```yaml
services:
  - type: web
    name: my-app
    disk:
      name: app-data
      mountPath: /data
      sizeGB: 1
```

## Monorepo Support
Set the **Root Directory** in service settings to the subfolder containing your Node app.
Render will run all commands from that directory.

## Zero-Downtime Deploys
Render performs zero-downtime rolling deploys. The old instance stays live until the
new instance passes all health checks, then traffic is shifted over.

## Private Services and Background Workers
Node.js apps can also be deployed as:
- **Private Service**: Internal API not exposed to the internet
- **Background Worker**: Long-running processes without HTTP (e.g., queue consumers)

```yaml
services:
  - type: worker        # background worker
    name: my-worker
    runtime: node
    buildCommand: npm install
    startCommand: node worker.js
```
