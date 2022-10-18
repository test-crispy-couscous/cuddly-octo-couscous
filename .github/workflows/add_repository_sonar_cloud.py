import argparse

import requests

from github import Github
from requests.auth import HTTPBasicAuth
from sonarqube import SonarCloudClient


def _enable_github_sonar_integration(github_access_token, repository_name, installation_id):
    github_api = Github(github_access_token)
    repository = github_api.get_repo(repository_name)
    repository_id = repository.id

    print(f"Retrieving repository ID given the parameter: {repository_name}")
    # PAT required scopes: repo, write:org, read:org
    github_api = Github(github_access_token)
    repository = github_api.get_repo(repository_name)
    repository_id = repository.id

    # This is not available in GitHub Python Library
    print(f"Adding the repository {repository_name}|{repository_id} to installation ID {installation_id}")
    headers = {"Authorization": f"token {github_access_token}", "Accept": "application/vnd.github.v3+json"}
    url = f"https://api.github.com/user/installations/{installation_id}/repositories/{repository_id}"
    result = requests.put(url, headers=headers)

    status_code = result.status_code
    if status_code not in [204, 304]:
        error_message = result.json()["message"]
        raise Exception(f"Something went wrong! Message given status code {status_code}: {error_message}")
    print("It's okay on Github!")

    return repository


def _add_sonar_cloud_project(
    repository, sonar_cloud_access_token, sonar_cloud_organization, sonar_cloud_quality_gate_id
):
    organization_key = repository.organization.login
    repository_name = repository.name
    project_key = f"{organization_key}_{repository_name}"
    repository_id = repository.id

    print("Checking if project exists on SonarCloud")

    sonar = SonarCloudClient("https://sonarcloud.io/", token=sonar_cloud_access_token)
    if any(sonar.projects.search_projects(projects=project_key, organization=sonar_cloud_organization)):
        raise Exception(f"Project {project_key} already exists on SonarCloud")

    print(f"Adding project {project_key} on SonarCloud")
    data = {"installationKeys": f"{organization_key}/{repository_name}|{repository_id}", "organization": sonar_cloud_organization}
    auth = HTTPBasicAuth(sonar_cloud_access_token, "")
    # Unfortunatly sonarcloud API does not has a public API to create a project bounded to a github repository.
    # As a workaround we use  an internal API.
    endpoint = "https://sonarcloud.io/api/alm_integration/provision_projects"
    result = requests.post(endpoint, data=data, auth=auth)
    if result.status_code not in [200, 304]:
        error_message = result.json()["errors"]
        raise Exception(f"Something went wrong! Message given status code {result.status_code}: {error_message}")

    print(f"Setting project {project_key} properties on SonarCloud")

    sonar.settings.update_setting_value(component=project_key, key="sonar.leak.period", value="previous_version")
    sonar.settings.update_setting_value(component=project_key, key="sonar.leak.period.type", value="previous_version")
    sonar.settings.update_setting_value(
        component=project_key, key="sonar.branch.longLivedBranches.regex", value="develop"
    )
    if sonar_cloud_quality_gate_id is not None:
        sonar.qualitygates.select_quality_gate_for_project(
            organization=sonar_cloud_organization, projectKey=project_key, gateId=sonar_cloud_quality_gate_id
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--github-access-token", type=str, required=True, help="The access token to call GitHub API")
    parser.add_argument(
        "--sonar-cloud-access-token", type=str, required=True, help="The access token to call SonarCloud API"
    )
    parser.add_argument(
        "--sonar-cloud-quality-gate-id", type=int, required=True, help="The Id of the target SonarCloud quality gate"
    )
    parser.add_argument(
        "--sonar-cloud-organization", type=str, required=True, help="The name of the SonarCloud organization"
    )
    parser.add_argument(
        "--installation-id",
        type=int,
        required=True,
        help="The installation ID of the SonarCloud App in your organization",
    )
    parser.add_argument("--repository-name", required=True, type=str, help="The target repository")

    args = parser.parse_args()

    repository = _enable_github_sonar_integration(args.github_access_token, args.repository_name, args.installation_id)
    _add_sonar_cloud_project(
        repository, args.sonar_cloud_access_token, args.sonar_cloud_organization, args.sonar_cloud_quality_gate_id
    )

    print("Done!")
