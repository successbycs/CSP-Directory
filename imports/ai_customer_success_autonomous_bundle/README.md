# AI Customer Success Autonomous Dev Starter

## What this starter gives you
- Four core docs for autonomous development
- Three agent prompts
- A milestone-based implementation plan
- A verification script
- Docker and devcontainer scaffolding

## Local workflow
1. Open repo in VS Code using WSL
2. Create and activate a Python virtualenv
3. Install requirements
4. Run the builder agent against the highest unfinished milestone
5. Run `scripts/verify_project.sh`
6. Review with reviewer and QA agents

## Container workflow
Build:
```bash
docker build -t ai-customer-success .
```

Run:
```bash
docker run -it --rm -p 8000:8000 --env-file .env ai-customer-success
```

## VS Code devcontainer workflow
- Ensure Docker Desktop or Docker Engine works from WSL
- Open the repo in VS Code
- Run: `Dev Containers: Reopen in Container`

## Important note
This starter pack is tailored to the architecture discussed in conversation. Before using it as source of truth, compare it to your actual repo and adjust milestone statuses, file paths, and commands.
