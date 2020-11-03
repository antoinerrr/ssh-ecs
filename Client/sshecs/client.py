#!/usr/bin/env python

import argparse
import getpass
import json
import os
import re
import requests
import signal
import shutil
import subprocess
import sys
import time

from simple_term_menu import TerminalMenu
from configparser import ConfigParser

VERSION = 1.2
ANIMATION = '|/-\\'


def debug(message):
    print('[DEBUG] ' + message)


def info(message):
    print('[INFO] ' + message)


def fatal(message):
    print('[FATAL] ' + message)
    sys.exit(1)


def clean_exit(sig=None, frame=None):
    sys.exit(0)


def init_config():
    info('Creating config file at ~/.ssh-ecs/config.cfg ...')

    conf_dir = os.path.expanduser('~') + '/.ssh-ecs'
    conf_file = conf_dir + '/config.cfg'

    if not os.path.exists(conf_dir):
        os.makedirs(conf_dir)

    if os.path.isfile(conf_file):
        fatal('Configuration file already exists')

    token = getpass.getpass(prompt='Please enter your GitHub token : ')

    parser = ConfigParser()

    parser.add_section('Server')
    parser.set('Server', 'Endpoint', 'your-server-endpoint')
    parser.add_section('Auth')
    parser.set('Auth', 'Token', token)
    parser.add_section('Filter')
    parser.set('Filter', 'Include_Products', '(My_Product_A|My_Product_B)')
    parser.set('Filter', 'Exclude_Products', '')
    parser.set('Filter', 'Include_services', '.*')
    parser.set('Filter', 'Exclude_services', '(datadog|dd-agent-.+)')
    parser.add_section('SSH')
    parser.set('SSH', 'Command', 'ssh')
    parser.set('SSH', 'Options', '-o StrictHostKeyChecking=no')
    parser.add_section('Debug')
    parser.set('Debug', 'Message', 'False')

    with open(conf_file, 'w') as fp:
        parser.write(fp)


def display_path(path):
    path = [p.split('/')[-1] for p in path]
    if path:
        indent = '  '
        result = '┣━━' + path[0]
        for p in path[1:]:
            result = '{}\n{}┗━{}'.format(result, indent, p)
            indent = indent + '  '
        return result + '\n\n'
    else:
        return ''


def ask_api(config, path, method='GET', header=False, payload=None):
    headers = {
        'Authorization': 'Bearer ' + config.get('Auth', 'Token')
    }
    try:
        if method == 'GET':
            response = requests.get(config.get('Server', 'Endpoint') + path, headers=headers)
        elif method == 'POST':
            response = requests.post(config.get('Server', 'Endpoint') + path, json=payload, headers=headers)
        else:
            raise Exception('Unhandled method ' + method)

        if config.get('Debug', 'Message') == 'True':
            debug('HTTP code = {}\n{}'.format(response.status_code, response.text))

        if response.status_code == 401:
            raise Exception('Auth key error (check your GitHub key in ~/.ssh-ecs/config.cfg)')
        elif response.status_code >= 400:
            raise Exception('Received HTTP code ({})'.format(response.status_code))

        json_output = json.loads(response.text)

        if header:
            return json_output, response.headers

        return json_output
    except Exception as e:
        fatal('Error while Querying API : {}'.format(e))


def ssh_connect(ip, container, ssh_command='ssh', ssh_options='', password=''):
    command = '{} -t {} ssh_bastion@{} "docker exec -it {} /bin/bash"'.format(ssh_command, ssh_options, ip, container)

    if shutil.which('sshpass') is not None:
        command = 'sshpass -p {} {}'.format(password, command)
    else:
        info('Your One Time Password is: ' + password)

    try:
        subprocess.run(command, shell=True, check=True)
    except Exception as e:
        fatal('Could not run SSH command ({})'.format(e))


def container_connect(parser, app, cluster, task, container):
    payload = {
        'task': task,
        'container': container
    }

    info = ask_api(parser, 'connect/{}/{}'.format(app, cluster), method='POST', payload=payload)

    if info.get('error', '') == 'Not_Allowed':
        terminal_menu = TerminalMenu(
            ['Yes', 'No'],
            title='You do not have access to this cluster. Do you want to ask for a temporary access ?'
        )
        ask_temp = terminal_menu.show()
        if ask_temp != 0:
            fatal('Action cancelled')

        ask_token = ask_api(parser, 'asktemp/{}/{}'.format(app, cluster), method='POST', payload=payload).get('token')

        count = 0
        wait = True
        while wait:
            print('Waiting for admin to confirm ' + ANIMATION[count % len(ANIMATION)], end='\r')
            count += 1
            status_request = ask_api(parser, 'checktemp/' + ask_token)
            if 'status' not in status_request:
                ip = status_request.get('ip')
                container = status_request.get('container')
                password = status_request.get('OTP')
                wait = False
            else:
                if count > 300:
                    fatal('No response from Admin')
                time.sleep(1)
    else:
        ip = info.get('ip')
        container = info.get('container')
        password = info.get('OTP')

    ssh_connect(
        ip,
        container,
        parser.get('SSH', 'Command'),
        parser.get('SSH', 'Options'),
        password
    )


def main():
    signal.signal(signal.SIGINT, clean_exit)

    arg_pars = argparse.ArgumentParser(
        description='''
            Connect to any container running on any ECS cluster,
            using your github personal token as an authentification key
        '''
    )
    arg_pars.add_argument(
        '--init',
        help='Create the base configuration file (~/.ssh-ecs/config.cfg)',
        action='store_true'
    )
    arg_pars.add_argument(
        '--allow',
        type=str,
        help='Allow admin to confirm a connection request')
    args = arg_pars.parse_args()

    if args.init:
        init_config()
        clean_exit()

    conf_file = os.path.expanduser('~') + '/.ssh-ecs/config.cfg'
    if not os.path.isfile(conf_file):
        fatal('Missing config file, please run "ssh-ecs --config"')

    config = ConfigParser()
    config.read(conf_file)

    if args.allow:
        print(ask_api(config, 'validatetemp/' + args.allow))
        clean_exit()

    menu, headers = ask_api(config, 'menu', header=True)

    if float(headers.get('Ssh-Tool-Version')) > VERSION:
        fatal(
            'Client is outdated, please update to the last version.' +
            'Follow process here: https://github.com/antoiner77/ssh-ecs'
        )

    def choose(elements, path, message, goback=True):
        title = 'User: {}\n{}{}'.format(headers.get('Ssh-Tool-User'), display_path(path), message)
        display = [e.split('/')[-1] for e in elements]
        if goback:
            display += ['<- Go back']
        idx = TerminalMenu(display, title=title).show()
        if idx is None or idx == len(elements):
            return None
        return elements[idx]

    def select_product():
        include = re.compile('^' + config.get('Filter', 'Include_Products') + '$')
        exclude = re.compile('^' + config.get('Filter', 'Exclude_Products') + '$')
        available_products = [product for product in menu.keys() if
                              include.match(product) and not exclude.match(product)]
        return choose(available_products, [], 'Select a product', goback=False)

    def select_environment(product):
        return choose(menu.get(product), [product], 'Select an environment')

    def select_service(product, env):
        all_services = ask_api(config, 'services/{}/{}'.format(product, env))
        if 'error' in all_services:
            fatal('Error while getting services')
        include = re.compile('^.+/' + config.get('Filter', 'Include_Services') + '$')
        exclude = re.compile('^.+/' + config.get('Filter', 'Exclude_Services') + '$')
        available_services = [s for s in all_services if include.match(s) and not exclude.match(s)]
        return choose(available_services, [product, env], 'Select a service')

    def select_task(product, env, service):
        all_tasks = ask_api(config, 'tasks/{}/{}'.format(product, env), method='POST',
                            payload={'service': service})
        if 'error' in all_tasks:
            fatal('Error while getting tasks')
        return choose(all_tasks, [product, env, service], 'Select a task')

    def select_container(product, env, service, task):
        all_containers = ask_api(config, 'containers/{}/{}'.format(product, env), method='POST',
                                 payload={'service': service, 'task': task})
        if 'error' in all_containers:
            fatal('Error while getting containers')
        if len(all_containers) == 1:
            return all_containers[0]
        else:
            return choose(all_containers, [product, env, service, task], 'Select a container')

    step = 'product'
    while step != 'finish':
        if step == 'product':
            selected_product = select_product()
            if selected_product:
                step = 'env'
            else:
                fatal('Operation cancelled')
        elif step == 'env':
            selected_env = select_environment(selected_product)
            step = 'service' if selected_env else 'product'
        elif step == 'service':
            selected_service = select_service(selected_product, selected_env)
            step = 'task' if selected_service else 'env'
        elif step == 'task':
            selected_task = select_task(selected_product, selected_env, selected_service)
            step = 'container' if selected_task else 'service'
        elif step == 'container':
            selected_container = select_container(selected_product, selected_env, selected_service, selected_task)
            step = 'finish' if selected_container else 'task'

    print('Connecting to container ...')
    print(display_path([selected_product, selected_env, selected_service, selected_task, selected_container]))
    container_connect(config, selected_product, selected_env, selected_task, selected_container)

    clean_exit()


if __name__ == '__main__':
    main()
