# Update this to force your clients to update (you will need to change the version in the client too)
VERSION = 1.2

# Enable requests cache, to cache response from the github API, it speed things up
CACHE_ENABLE = True
# Do you want to log the connection to datadog ? Do it here
LOG_DATADOG = True

# Name of your github org
GITHUB_ORG = "My-Org"
# Main user token to check github groups of user (need read on admin:org)
GITHUB_ADMIN_TOKEN = "token"
# If you want to log to datadog, http intake url v1 here.
DATADOG_URL = "https://http-intake.logs.datadoghq.eu/v1/input/KEY"
# Where to send the "Blabla want to access xx env" message in slack
SLACK_URL = "https://hooks.slack.com/services/KEY"
# Address for the vault cluster
VAULT_ADDR = "https://vault.my.website"
# A token to use vault, with rights to create OTP password
VAULT_TOKEN = "token"
# Path to the OTP vault secret engine
VAULT_SECRET = "ssh/creds/otp_key_role"

# The menu to display to your users
# First key is the product
# Second key is the cluster name (need to exist in aws)
MENU = {
  "Service 1": [
      "prod-service-1"
  ],
  "Service 2": [
      "uat-srv2",
      "pp-srv2",
      "prod-srv2"
  ]
}

# The big config, basically taking all the env you have set up in the menu, and mapping a list of group to them
# The allow_admin config is the list of the groups allowed to grand access to a user over slack
# The aws key is set to root if your cluster is in the same account as this script, or is set to the arn of a role to 
# assume to access an other account
# The region key is the region where we can find the cluster
MAP_GROUP = {
  "allow_admin": {
      "admin": [
          "devops"
      ]
  },
  "Service 1": {
      "aws": "root",
      "region": "eu-west-1",
      "prod-service-1": [
          "service1-dev",
          "devops"
      ]
  },
  "Service 2": {
      "aws": "arn:aws:iam::My2ndAccount:role/MyRole",
      "region": "eu-west-1",
      "uat-srv2": [
          "product",
          "srv2-dev",
          "devops"
      ],
      "pp-srv2": [
          "srv2-dev",
          "devops"
      ]
      "prod-srv2": [
          "devops"
      ]
  }
}
