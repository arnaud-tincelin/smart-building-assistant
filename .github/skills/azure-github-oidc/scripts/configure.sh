#!/usr/bin/env bash
set -euo pipefail

for command_name in az gh git; do
  if ! command -v "$command_name" > /dev/null 2>&1; then
    echo "Missing required command: $command_name" >&2
    exit 1
  fi
done

if ! az account show > /dev/null 2>&1; then
  echo "Azure CLI is not signed in. Run: az login" >&2
  exit 1
fi

if ! gh auth status > /dev/null 2>&1; then
  echo "GitHub CLI is not signed in. Run: gh auth login" >&2
  exit 1
fi

repository="${GITHUB_REPOSITORY:-$(gh repo view --json nameWithOwner --jq .nameWithOwner)}"
if [[ "$repository" != */* ]]; then
  echo "Could not resolve the GitHub repository owner and name." >&2
  exit 1
fi

branch="${GITHUB_BRANCH:-main}"
location="${AZURE_LOCATION:-}"
if [[ -z "$location" ]]; then
  location="$(gh variable get AZURE_LOCATION --repo "$repository" 2> /dev/null || true)"
fi
location="${location:-eastus2}"

root="$(git rev-parse --show-toplevel)"
template_file="$root/infra/github-oidc.bicep"
deployment_name="${AZURE_GITHUB_DEPLOYMENT_NAME:-buildingassist-github-cicd}"
identity_resource_group="${AZURE_GITHUB_IDENTITY_RESOURCE_GROUP:-rg-buildingassist-cicd}"
identity_name="${AZURE_GITHUB_IDENTITY_NAME:-id-buildingassist-github}"
github_owner="${repository%%/*}"
github_repository="${repository#*/}"
subscription_id="$(az account show --query id --output tsv)"
tenant_id="$(az account show --query tenantId --output tsv)"

if [[ ! -f "$template_file" ]]; then
  echo "Missing Bicep template: $template_file" >&2
  exit 1
fi

echo "Repository   : $repository"
echo "Branch       : $branch"
echo "Subscription : $subscription_id"
echo "Location     : $location"
echo "Identity     : $identity_name"

deployment_parameters=(
  "location=$location"
  "githubOwner=$github_owner"
  "githubRepository=$github_repository"
  "githubBranch=$branch"
  "identityResourceGroupName=$identity_resource_group"
  "identityName=$identity_name"
)

echo "Previewing Azure identity and RBAC changes..."
az deployment sub what-if \
  --name "$deployment_name" \
  --location "$location" \
  --template-file "$template_file" \
  --parameters "${deployment_parameters[@]}"

echo "Applying Azure identity and RBAC changes..."
az deployment sub create \
  --name "$deployment_name" \
  --location "$location" \
  --template-file "$template_file" \
  --parameters "${deployment_parameters[@]}" \
  --output none

client_id="$(az identity show --resource-group "$identity_resource_group" --name "$identity_name" --query clientId --output tsv)"
if [[ -z "$client_id" || -z "$subscription_id" || -z "$tenant_id" ]]; then
  echo "Azure returned an empty identity or account value; GitHub variables were not changed." >&2
  exit 1
fi

echo "Configuring GitHub Actions variables..."
gh variable set AZURE_CLIENT_ID --repo "$repository" --body "$client_id"
gh variable set AZURE_TENANT_ID --repo "$repository" --body "$tenant_id"
gh variable set AZURE_SUBSCRIPTION_ID --repo "$repository" --body "$subscription_id"
gh variable set AZURE_LOCATION --repo "$repository" --body "$location"

federated_subject="$(az identity federated-credential show \
  --resource-group "$identity_resource_group" \
  --identity-name "$identity_name" \
  --name "github-$branch" \
  --query subject \
  --output tsv)"
expected_subject="repo:$repository:ref:refs/heads/$branch"
if [[ "$federated_subject" != "$expected_subject" ]]; then
  echo "Federated credential subject does not match $expected_subject." >&2
  exit 1
fi

echo
echo "GitHub OIDC configuration verified."
echo "Federated subject: $federated_subject"
echo "Azure roles: Contributor, Role Based Access Control Administrator"
echo "GitHub variables: AZURE_CLIENT_ID, AZURE_TENANT_ID, AZURE_SUBSCRIPTION_ID, AZURE_LOCATION"
