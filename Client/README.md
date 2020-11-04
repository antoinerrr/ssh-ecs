# SSH-ECS
### Installation

sshecs required python3 to run.

```sh
$ git clone git@github.com:antoiner77/ssh-ecs-client.git
$ cd ssh-ecs-client/Client
$ pip3 install .
```

Warning, make sure you have python3 installed, and that there is no path issue message during the pip command, if there is, add the path in your bash profile 

To init the script:

```sh
$ sshecs --init
```

Go to https://github.com/settings/tokens/new and create a new token, we only need `read:user` and `user:email` scopes, from the "user" categorie

Then you can add your token in the `~/.ssh-ecs/config.cfg` file, ligne 4

Start the script:

```sh
$ sshecs
```

### Update

```sh
$ cd ssh-ecs/Client
$ git pull
$ pip3 install .
```
