########
# Copyright (c) 2014 GigaSpaces Technologies Ltd. All rights reserved
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# * See the License for the specific language governing permissions and
#    * limitations under the License.

import os
import copy
import time
import uuid
from contextlib import contextmanager

import requests
from retrying import retry
from fabric.context_managers import settings as fab_env
from fabric.context_managers import cd

from cloudify.workflows import local
from cloudify_cli import constants as cli_constants
from cloudify_rest_client import CloudifyClient
import fabric.api as fab
from fabric.api import env

from cosmo_tester.framework.testenv import TestCase

HELLO_WORLD_EXAMPLE_NAME = 'cloudify-hello-world-example'
EXAMPLE_URL = 'https://github.com/cloudify-cosmo/{0}/archive/{1}.tar.gz'
IMPLEMENTATION_MSG = 'this should be implemented in inheriting classes'


class TestCliPackage(TestCase):

    @property
    def package_parameter_name(self):
        raise Exception(IMPLEMENTATION_MSG)

    @property
    def cli_package_url(self):
        return os.environ[self.package_parameter_name]

    @property
    def client_cfy_work_dir(self):
        raise Exception(IMPLEMENTATION_MSG)

    @property
    def propertsadawed(self):
        raise Exception(IMPLEMENTATION_MSG)

    @property
    def client_user(self):
        raise Exception(IMPLEMENTATION_MSG)

    @property
    def image_name(self):
        raise Exception(IMPLEMENTATION_MSG)

    def get_local_env_outputs(self):
        self.public_ip_address = \
            self.local_env.outputs()['vm_public_ip_address']

    def is_install_plugins(self):
        return False

    def additional_setup(self):
        if self.package_parameter_name not in os.environ:
            raise ValueError(
                '{0} environment variable not set'
                .format(self.package_parameter_name))

        blueprint_filename = self.local_env_blueprint_file_name
        blueprint_path = os.path.join(os.path.dirname(__file__),
                                      'resources',
                                      blueprint_filename)
        self.prefix = '{0}-cli-host'.format(self.test_id)
        self.bootstrap_prefix = 'cloudify-{0}'.format(self.test_id)

        self.inputs = self.get_local_env_inputs()
        self.bootstrap_inputs = self.get_bootstrap_inputs()
        self.deployment_inputs = self.get_deployment_inputs()

        self.branch = os.environ.get('BRANCH_NAME_CORE', 'master')
        self.logger.info('Using branch/tag: {0}'.format(self.branch))

        self.logger.info('initialize local env for running the '
                         'blueprint that starts a vm')
        self.local_env = local.init_env(
            blueprint_path,
            inputs=self.inputs,
            name=self._testMethodName,
            ignored_modules=cli_constants.IGNORED_LOCAL_WORKFLOW_MODULES)

        self.logger.info('Starting vm to install CLI package on it later on')
        self.addCleanup(self.cleanup)
        self.local_env.execute('install',
                               task_retries=40,
                               task_retry_interval=30)

        self.get_local_env_outputs()
        self.logger.info('Outputs: {0}'.format(self.local_env.outputs()))

        env.update({
            'timeout': 30,
            'user': self.client_user,
            'key_filename': self.inputs['key_pair_path'],
            'host_string': self.public_ip_address,
            'connection_attempts': 10,
            'abort_on_prompts': True
        })

    def get_local_env_inputs(self):
        return {
            'prefix': self.prefix,
            'external_network': self.env.external_network_name,
            'os_username': self.env.keystone_username,
            'os_password': self.env.keystone_password,
            'os_tenant_name': self.env.keystone_tenant_name,
            'os_region': self.env.region,
            'os_auth_url': self.env.keystone_url,
            'image_name': self.image_name,
            'flavor': self.env.medium_flavor_id,
            'key_pair_path': '{0}/{1}-keypair.pem'.format(self.workdir,
                                                          self.prefix)
        }

    def get_bootstrap_inputs(self):
        return {
            'keystone_username': self.env.keystone_username,
            'keystone_password': self.env.keystone_password,
            'keystone_tenant_name': self.env.keystone_tenant_name,
            'keystone_url': self.env.keystone_url,
            'region': self.env.region,
            'image_id': self.env.centos_7_image_id,
            'flavor_id': self.env.medium_flavor_id,
            'external_network_name': self.env.external_network_name,
            'manager_server_name': self.env.management_server_name,
            'management_network_name': self.env.management_network_name,
            'manager_public_key_name': '{0}-manager-keypair'.format(
                self.prefix),
            'agent_public_key_name': '{0}-agent-keypair'.format(
                self.prefix),
        }

    def local_env_blueprint_file_name(self):
        raise Exception("Each blueprint should specify it's local env "
                        "blueprint")

    def get_deployment_inputs(self):
        return {
            'agent_user': 'ubuntu',
            'image': self.env.ubuntu_trusty_image_id,
            'flavor': self.env.medium_flavor_id
        }

    def setUp(self):
        super(TestCliPackage, self).setUp()
        self.additional_setup()

    def _execute_command(self, cmd, within_cfy_env=False, sudo=False,
                         log_cmd=True, retries=0, warn_only=False):
        if within_cfy_env:
            cmd = 'source {0}/env/bin/activate && cfy {1}' \
                  .format(self.client_cfy_work_dir, cmd)

        if log_cmd:
            self.logger.info('Executing command: {0}'.format(cmd))
        else:
            self.logger.info('Executing command: ***')

        while True:
            if sudo:
                out = fab.sudo(cmd, warn_only=warn_only)
            else:
                out = fab.run(cmd, warn_only=warn_only)

            self.logger.info("""Command execution result:
    Status code: {0}
    STDOUT:
    {1}
    STDERR:
    {2}""".format(out.return_code, out, out.stderr))
            if out.succeeded or (warn_only and retries == 0):
                return out
            else:
                if retries > 0:
                    time.sleep(30)
                    retries -= 1
                else:
                    raise Exception('Command: {0} exited with code: '
                                    '{1}. Tried {2} times.'
                                    .format(cmd, out.return_code, retries + 1))

    def install_cli(self):
        self.logger.info('installing cli...')

        self._get_resource(self.cli_package_url, ops='-LO', sudo=True)
        self._get_resource('https://raw.githubusercontent.com/pypa/'
                           'pip/master/contrib/get-pip.py', ops='-L',
                           pipe_command='sudo python2.7 -')
        self._execute_command('pip install virtualenv', sudo=True)

        last_ind = self.cli_package_url.rindex('/')
        package_name = self.cli_package_url[last_ind + 1:]
        self._execute_command('rpm -i {0}'.format(package_name), sudo=True)

    def _get_resource(self, resource_address, ops='', sudo=False,
                      pipe_command=''):
        if pipe_command:
            pipe_command = "| {0}".format(pipe_command)

        return self._execute_command('curl {0} {1} {2}'
                                     .format(ops, resource_address,
                                             pipe_command),
                                     sudo=sudo)

    def change_to_tarzan_urls(self):
        pass

    def add_dns_nameservers_to_manager_blueprint(self, local_modify_script):
        remote_modify_script = os.path.join(self.client_cfy_work_dir,
                                            'modify.py')
        self.logger.info(
            'Uploading {0} to {1} on manager...'.format(local_modify_script,
                                                        remote_modify_script))
        fab.put(local_modify_script, remote_modify_script, use_sudo=True)
        self.logger.info(
            'Adding DNS name servers to remote manager blueprint...')
        fab.run('sudo python {0} {1}'.format(
            remote_modify_script, self.test_manager_blueprint_path))

    def get_manager_blueprint_file_name(self):
        return 'openstack-manager-blueprint.yaml'

    def prepare_manager_blueprint(self):
        self.manager_blueprints_repo_dir = '{0}/cloudify-manager-blueprints' \
                                           '-commercial/' \
                                           .format(self.client_cfy_work_dir)
        self.test_manager_blueprint_path = \
            os.path.join(self.manager_blueprints_repo_dir,
                         self.get_manager_blueprint_file_name())

        self.local_bootstrap_inputs_path = \
            self.cfy._get_inputs_in_temp_file(self.bootstrap_inputs,
                                              self._testMethodName)
        self.remote_bootstrap_inputs_path = \
            os.path.join(self.client_cfy_work_dir, 'bootstrap_inputs.json')
        fab.put(self.local_bootstrap_inputs_path,
                self.remote_bootstrap_inputs_path, use_sudo=True)

        self.change_to_tarzan_urls()

    def bootstrap_manager(self):
        self.logger.info('Bootstrapping Cloudify manager...')

        self._execute_command('init', within_cfy_env=True)

        install_plugins = ''
        if self.is_install_plugins():
            install_plugins = '--install-plugins'
        out = self._execute_command(
            'bootstrap -p {0} -i {1} {2}'.format(
                self.test_manager_blueprint_path,
                self.remote_bootstrap_inputs_path,
                install_plugins),
            within_cfy_env=True)

        self.assertIn('bootstrapping complete', out,
                      'Bootstrap has failed')

        self.manager_ip = self._manager_ip()
        self.client = CloudifyClient(self.manager_ip)
        self.addCleanup(self.teardown_manager)

    def get_hello_world_url(self):
        return EXAMPLE_URL.format(HELLO_WORLD_EXAMPLE_NAME, self.branch)

    def get_app_blueprint_file(self):
        return 'blueprint.yaml'

    def publish_hello_world_blueprint(self):
        hello_world_url = self.get_hello_world_url()
        blueprint_id = 'blueprint-{0}'.format(uuid.uuid4())
        self.logger.info('Publishing hello-world example from: {0} [{1}]'
                         .format(hello_world_url, blueprint_id))
        self._execute_command('blueprints publish-archive '
                              '-l {0} -n {1} -b {2}'
                              .format(hello_world_url,
                                      self.get_app_blueprint_file(),
                                      blueprint_id),
                              within_cfy_env=True)
        return blueprint_id

    def prepare_deployment(self):
        self.local_deployment_inputs_path = \
            self.cfy._get_inputs_in_temp_file(self.deployment_inputs,
                                              self._testMethodName)
        self.remote_deployment_inputs_path = \
            os.path.join(self.client_cfy_work_dir,
                         'deployment_inputs.json')
        fab.put(self.local_deployment_inputs_path,
                self.remote_deployment_inputs_path, use_sudo=True)

    def create_deployment(self, blueprint_id):
        deployment_id = 'deployment-{0}'.format(uuid.uuid4())
        self.prepare_deployment()

        self.logger.info('Creating deployment: {0}'.format(deployment_id))
        self._execute_command(
            'deployments create -b {0} -d {1} -i {2}'
            .format(blueprint_id, deployment_id,
                    self.remote_deployment_inputs_path),
            within_cfy_env=True)

        return deployment_id

    def install_deployment(self, deployment_id):
        self.logger.info(
            'Waiting for 15 seconds before installing deployment...')
        time.sleep(15)
        self.logger.info('Installing deployment...')
        self._execute_command('executions start -d {0} -w install'
                              .format(deployment_id),
                              within_cfy_env=True, retries=2)

    def uninstall_deployment(self):
        self.cfy._wait_for_stop_dep_env_execution_if_necessary(
            self.deployment_id)
        self.logger.info('Uninstalling deployment...')
        self._execute_command('executions start -d {0} -w uninstall'
                              .format(self.deployment_id), within_cfy_env=True)

    def _test_cli_package(self):
        self.install_cli()
        self.prepare_manager_blueprint()
        self.add_dns_nameservers_to_manager_blueprint(
            os.path.join(os.path.dirname(__file__),
                         'resources/add_nameservers_to_subnet.py'))
        self.bootstrap_manager()
        blueprint_id = self.publish_hello_world_blueprint()
        self.deployment_id = self.create_deployment(blueprint_id)
        self.addCleanup(self.uninstall_deployment)
        self.install_deployment(self.deployment_id)
        self.assert_deployment_working(
            self._get_app_property('http_endpoint'))

    def _manager_ip(self):
        nova_client, _, _ = self.env.handler.openstack_clients()
        for server in nova_client.servers.list():
            if server.name == self.env.management_server_name:
                for network, network_ips in server.networks.items():
                    if network == self.env.management_network_name:
                        return network_ips[1]
        self.fail('Failed finding manager ip')

    def _get_app_property(self, property_name):
        outputs_resp = self.client.deployments.outputs.get(self.deployment_id)
        return outputs_resp['outputs'][property_name]

    @retry(stop_max_attempt_number=3, wait_fixed=3000)
    def assert_deployment_working(self, url):
        self.logger.info('Asserting deployment deployed successfully')
        server_page_response = requests.get(url)
        self.assertEqual(200, server_page_response.status_code,
                         'Failed to get home page of app')
        self.logger.info('Example deployed successfully')

    def cleanup(self):
        self.local_env.execute('uninstall',
                               task_retries=40,
                               task_retry_interval=30)

    def teardown_manager(self):
        self.logger.info('Tearing down Cloudify manager...')
        self._execute_command('teardown -f --ignore-deployments',
                              within_cfy_env=True)

    @contextmanager
    def dns(self, dns_name_servers=('8.8.8.8', '8.8.4.4')):
        """
        Enables setting custom dns servers on the local machine.
        This is useful mainly when the bootstrap doesn't contain a
        dns_nameservers.

        :param execute_command: the command executer (belong to some machine)
        :param logger: logger object on which to log.
        :param dns_name_servers: an iterable of dns addresses.
        defaults to ('8.8.8.8', '8.8.4.4').
        :return: None
        """
        self._execute_command("chmod +w /etc/resolv.conf", sudo=True)

        for server in dns_name_servers:
            self.logger.info('Adding {0} to dns list'.format(server))
            self._execute_command("echo 'nameserver {0}' >> /etc/resolv.conf"
                                  .format(server), sudo=True)

        yield

        for server in dns_name_servers:
            self.logger.info('Removing {0} from dns list'.format(server))
            self._execute_command(
                "sed -i '/nameserver {0}/c\\' /etc/resolv.conf".format(server),
                sudo=True)

    def wait_for_vm_to_become_ssh_available(self, env_settings, executor,
                                            retries=10, retry_interval=30,
                                            timeout=20):
        """
        Asserts that a machine received the ssh key for the key manager, and it is
        no ready to be connected via ssh.
        :param env_settings: The fabric setting for the remote machine.
        :param executor: An executer function, which executes code on the remote
        machine.
        :param retries: number of time to check for availability. default to 10.
        :param retry_interval: length of the intervals between each try. defaults
        to 30.
        :param timeout: timeout for each check try. default to 60.
        :return: None
        """
        local_env_setting = copy.deepcopy(env_settings)
        local_env_setting.update({'abort_exception': FabException})
        local_env_setting.update({'timeout': timeout})
        if self.logger:
            self.logger.info('Waiting for ssh key to register on the vm...')
        while retries >= 0:
            try:
                with fab_env(**local_env_setting):
                    executor('echo Success')
                    if self.logger:
                        self.logger.info('Machine is ready to be logged in...')
                    return
            except FabException as e:
                if retries == 0:
                    raise e
                else:
                    if self.logger:
                        self.logger.info(
                            'Machine is not yet ready, waiting for {0} '
                            'secs and trying again'.format(retry_interval))
                    retries -= 1
                    time.sleep(retry_interval)
                    continue

    def install_python27(self):
        self.wait_for_vm_to_become_ssh_available(env, self._execute_command,
                                                 self.logger)
        with self.dns():

            self.logger.info('installing python 2.7...')

            self._execute_command('yum -y update', sudo=True)
            self._execute_command('yum install yum-downloadonly wget '
                                  'mlocate yum-utils python-devel '
                                  'libyaml-devel ruby rubygems '
                                  'ruby-devel make gcc git -y', sudo=True)
            self._execute_command('yum groupinstall -y \'development '
                                  'tools\'', sudo=True)
            self._execute_command('yum install -y zlib-devel bzip2-devel '
                                  'openssl-devel xz-libs', sudo=True)
            self._execute_command('curl -LO http://www.python.org/ftp/python/'
                                  '2.7.8/Python-2.7.8.tar.xz', sudo=True)
            self._execute_command('xz -d Python-2.7.8.tar.xz', sudo=True)
            self._execute_command('tar -xvf Python-2.7.8.tar', sudo=True)
            with cd('Python-2.7.8'):
                self._execute_command('./configure --prefix=/usr', sudo=True)
                self._execute_command('make', sudo=True)
                self._execute_command('make altinstall', sudo=True)
            self._execute_command('alias python=python2.7', sudo=True)


class FabException(Exception):
    """
    Custom exception which replaces the standard SystemExit which is raised
    by fabric on errors.
    """
    pass
