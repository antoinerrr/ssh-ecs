# SSH-ECS-SERVER

## Installation

### Server
sshecs server need python3 to run.

```sh
$ git clone git@github.com:meero-com/ssh-ecs-server.git
$ cd ssh-ecs-server
$ pip3 install -r requirements.txt
```

Lot of probably useless packages here, it work, optimise if you want

To start the server:

```sh
$ python3 server-http.py
```

It's not recommanded to run the server like this for production, better use a webserver in front

You will need to change the config in `serverSettings.py` to fit your needs

By default, for caching we use sqlite (bruh ugly) and tinydb to manage the conenctions requests (local json file)
Both this can be easily switch to something more robust like redit and a real database (first few lines of the script) Please open a PR if you do it, me i don't really need it :) .

### Vault

Follow this: https://www.vaultproject.io/docs/secrets/ssh/one-time-ssh-passwords it will work just fine ;) for allowed cidr put all the cidr for all your env, for default user put `ssh_bastion` change the default ttl to something small, 3 minutes is fine.

### Iam 

We need to have a role attach to the instance running the server with this:

```
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "VisualEditor0",
            "Effect": "Allow",
            "Action": [
                "ec2:DescribeInstances",
                "ecs:ListContainerInstances",
                "ecs:ListServices",
                "ecs:ListTasks",
                "ecs:DescribeTasks",
                "sts:AssumeRole",
                "ecs:DescribeServices",
                "ecs:DescribeContainerInstances",
                "ecs:ListClusters",
            ],
            "Resource": "*"
        }
    ]
}
```

### EC2 user data 
(tested only with aws ami for ecs)

Change all the caps things to make it work, it help you create a user and only allow this user to docker exec

```
#cloud-config
repo_update: true
repo_upgrade: all

packages:
  - ALL YOU NEED HERE

users:
  - name: "ec2-user"
    gecos: "EC2 Default User"
    groups:
      - "wheel"
    shell: "/bin/bash"
    sudo:
      - "ALL=(ALL) NOPASSWD:ALL"
    ssh-authorized-keys: 
      - " YOUR MAIN SSH KEY TO KEEP AN ACCESS TO THE SERVER"
  - name: "ssh_bastion"
    gecos: "SSH Bastion"
    shell: "/usr/local/bin/ssh_bastion"

write_files:
  - path: "/etc/profile.d/custom.sh"
    content: |
      if [ -n "$BASH_VERSION" -o -n "$KSH_VERSION" -o -n "$ZSH_VERSION" ]; then
        alias c='clear'
        alias df='df -h'
        alias du='du -h'
        alias la='ls -a'
        alias ll='ls -l'
        alias lla='ls -la'
        alias ls='ls --classify --tabsize=0 --literal --show-control-chars --human-readable --color=auto'
        alias mc='mc -d'
        red="\[\033[1;31m\]"
        green="\[\033[1;32m\]"
        blue="\[\033[1;34m\]"
        yellow="\[\033[1;33m\]"
        cyan="\[\033[1;36m\]"
        pink="\[\033[1;35m\]"
        white="\[\033[1;37m\]"
        default="\[\033[0;m\]"
        export PROMPT_COMMAND='if [ $? -ne 0 ];then ERROR_FLAG=1;else ERROR_FLAG=;fi;'
        if [ "$(id -u)" -eq 0 ]; then
            export PS1=$${default}'\t ['$${red}'\u@\h'$${default}']['$${green}'\w'$${default}']$${ERROR_FLAG:+'$${red}'}#> $${ERROR_FLAG:+'$${default}'}'
        else
            export PS1=$${default}'\t ['$${blue}'\u@\h'$${default}']['$${green}'\w'$${default}']$${ERROR_FLAG:+'$${red}'}\$> $${ERROR_FLAG:+'$${default}'}'
        fi
        unset red green blue yellow cyan pink white default
      fi
  - path: "/etc/ecs/ecs.config"
    content: |
      ECS_CLUSTER=${cluster_name}
  - path: "/usr/local/bin/ssh_bastion"
    permissions: "0755"
    content: |
      #!/bin/bash
      
      shift
      
      command=$1
      pat='docker exec -it ([a-z0-9]+) /bin/bash'
      
      [[ $command =~ $pat ]]
      
      if [ "$${BASH_REMATCH[0]}" != "" ]; then
          $@
      else
          echo "Invalid command"
          exit 1
      fi
  - path: "/etc/pam.d/sshd"
    permissions: "0755"
    content: |
      #%PAM-1.0
      # Disabled since we use Vault SSH Helper
      # auth       required    pam_sepermit.so
      # auth       substack     password-auth
      # auth       include      postlogin
      # Used with polkit to reauthorize users in remote sessions
      #-auth      optional     pam_reauthorize.so prepare
      account    required     pam_nologin.so
      account    include      password-auth
      password   include      password-auth
      # pam_selinux.so close should be the first session rule
      session    required     pam_selinux.so close
      session    required     pam_loginuid.so
      # pam_selinux.so open should only be followed by sessions to be executed in the user context
      session    required     pam_selinux.so open env_params
      session    required     pam_namespace.so
      session    optional     pam_keyinit.so force revoke
      session    include      password-auth
      session    include      postlogin
      # Used with polkit to reauthorize users in remote sessions
      -session   optional     pam_reauthorize.so prepare
      # Used with Vault SSH Helper
      auth requisite pam_exec.so quiet expose_authtok log=/var/log/vault-ssh.log /usr/local/bin/vault-ssh-helper -config=/etc/vault-ssh-helper.d/config.hcl
      auth optional pam_unix.so not_set_pass use_first_pass nodelay
  - path: "/etc/vault-ssh-helper.d/config.hcl"
    permissions: "0600"
    content: |
      vault_addr = "VAULT ADDRESS"
      ssh_mount_point = "ssh"
      ca_cert = "/etc/vault-ssh-helper.d/vault.crt"
      tls_skip_verify = false
      allowed_roles = "*"
  - path: "/etc/vault-ssh-helper.d/vault.crt"
    permissions: "0600"
    content: |
      -----BEGIN CERTIFICATE-----
      VAULT CERTIFICATE
      -----END CERTIFICATE-----
bootcmd:
  - "sed -i -e 's/ChallengeResponseAuthentication no/ChallengeResponseAuthentication yes/g' /etc/ssh/sshd_config"
  - "sed -i -e 's/UsePAM no/UsePAM yes/g' /etc/ssh/sshd_config"
  - "sed -i -e 's/PasswordAuthentication yes/PasswordAuthentication no/g' /etc/ssh/sshd_config"

runcmd:
  - "sh -c 'for user in ec2-user ssh_bastion; do usermod -a -G docker $${user}; done'"
  - "sh -c 'grep -qxF '/usr/local/bin/ssh_bastion' /etc/shells || echo /usr/local/bin/ssh_bastion >> /etc/shells'"
  - "wget https://releases.hashicorp.com/vault-ssh-helper/0.2.0/vault-ssh-helper_0.2.0_linux_amd64.zip"
  - "unzip -o vault-ssh-helper_0.2.0_linux_amd64.zip -d /usr/local/bin/"
  - "rm -f vault-ssh-helper_0.2.0_linux_amd64.zip"
```