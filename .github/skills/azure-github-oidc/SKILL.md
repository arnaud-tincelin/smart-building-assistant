---
name: azure-github-oidc
description: Configure or repair secretless GitHub Actions access to Azure for this repository using GitHub OIDC and a user-assigned managed identity. Use for initial setup, reconfiguration, federation repair, GitHub Actions variable repair, or Azure RBAC repair for the deployment workflow.
allowed-tools: Bash(az:*) Bash(bash:*) Bash(gh:*) Bash(git:*)
---

# Azure and GitHub OIDC

Configure the connection used by `.github/workflows/deploy.yml`. The result must
remain secretless: GitHub exchanges its OIDC token for the Azure user-assigned
managed identity defined by `infra/github-oidc.bicep`.

## Workflow

1. Read `.github/workflows/deploy.yml` and `infra/github-oidc.bicep` before making
   changes. Preserve their repository, branch, environment, and identity names.
2. Confirm `az account show` and `gh auth status` succeed. If either command needs
   interactive authentication, ask the user to complete it directly in the terminal.
   Never request or handle a password, token, PAT, or client secret.
3. Resolve the target repository with `gh repo view`, the subscription with
   `az account show`, and the location from `AZURE_LOCATION` or the existing GitHub
   variable. Resolve the repository subject prefix from GitHub's OIDC customization
   endpoint and validate it against the repository's numeric IDs. Show these
   non-secret targets before changing cloud resources.
4. Run the helper from the repository root:

   ```bash
   bash .github/skills/azure-github-oidc/scripts/configure.sh
   ```

5. Report the Azure deployment state, managed identity name, federated subject,
   role names, and GitHub variable names. Do not print variable values or tokens.

## Defaults

The helper is idempotent and uses the repository's single demo environment:

| Setting                 | Default                                       |
| ----------------------- | --------------------------------------------- |
| GitHub branch           | `main`                                        |
| Azure location          | Existing GitHub variable, otherwise `eastus2` |
| Azure deployment        | `buildingassist-github-cicd`                  |
| Identity resource group | `rg-buildingassist-cicd`                      |
| Managed identity        | `id-buildingassist-github`                    |

Override a default only when the user explicitly changes the corresponding target:

```bash
GITHUB_REPOSITORY=owner/repository \
GITHUB_BRANCH=main \
AZURE_LOCATION=eastus2 \
bash .github/skills/azure-github-oidc/scripts/configure.sh
```

## Security

- Use `infra/github-oidc.bicep`; do not replace it with imperative Azure resource
  creation.
- Always run the subscription deployment `what-if` before applying it.
- Trust only the exact repository subject prefix reported by GitHub, followed by
  `:ref:refs/heads/<branch>`; never use a wildcard subject.
- Store tenant, subscription, client, and location IDs as GitHub variables, not
  secrets. They are identifiers, not credentials.
- Never create an application client secret or a GitHub PAT.
