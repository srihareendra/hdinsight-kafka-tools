import logging, os, sys, time, traceback
from kafka_testutils import KafkaTestUtils

logger = logging.getLogger(__name__)
debug = False

def main(ktu):
    ssh_username = ''
    if len(sys.argv) > 1:
        ssh_username = sys.argv[1]
    logger.info('ssh_username = ' + ssh_username)

    script_dir = os.path.dirname(__file__)

    ssh_key_param = ''
    ssh_password_param = ''

    ssh_password = ''
    ssh_key_file = ''
    if len(sys.argv) > 2:
        ssh_password = sys.argv[2]

    if ssh_password:
        if os.path.exists(ssh_password):
            ssh_key_file = ssh_password
        elif os.path.exists(os.path.join(script_dir, ssh_password)):
            ssh_key_file = os.path.join(script_dir, ssh_password)

    if os.path.exists(ssh_key_file):
        logger.info('ssh_key_file = ' + ssh_key_file)
        stdout, stderr = ktu.runShellCommand('chmod 600 {0}'.format(ssh_key_file))
        ssh_key_param = '-i {0}'.format(ssh_key_file)
    else:
        logger.info('ssh_password = ' + ssh_password)
        ssh_password_param = 'sshpass -p {0} '.format(ssh_password)
        stdout, stderr = ktu.runShellCommand('sudo apt-get install sshpass')


    zookeepers, broker_hosts, brokers = ktu.getBrokerInformation()
    errored_brokers = []

    for broker_host in broker_hosts:
        if broker_host:
            logger.info('\nPatching broker host: {0}\n-----------------------------------'.format(broker_host))
            try:
                #Copy the deb packages to nodes requiring patching
                stdout, stderr = ktu.runShellCommand('{0}scp {1} -o StrictHostKeyChecking=no ~/*.deb {2}@{3}:~/'
                                                     .format(ssh_password_param, ssh_key_param, ssh_username, broker_host))
                #Copy the newly built jars
                stdout, stderr = ktu.runShellCommand('{0}scp {1} -o StrictHostKeyChecking=no ~/kafka*.jar {2}@{3}:~/'
                                                     .format(ssh_password_param, ssh_key_param, ssh_username, broker_host))
                #Kill the recovery service so that it does not reboot the nodes
                cmd ='sudo kill -9 \$(cat /var/run/kafkarecoveryservice.pid) ; sudo rm -rf /var/run/kafkarecoveryservice.pid ; '
                stdout, stderr = ktu.runShellCommand('{0}ssh {1} -o StrictHostKeyChecking=no {2}@{3} "{4}"'
                                                     .format(ssh_password_param, ssh_key_param, ssh_username, broker_host, cmd))
                try:
                    #Stop Ambari and Kafka service
                    cmd = 'sudo service ambari-agent stop ; sudo kafka stop'.format(ssh_username)
                    stdout, stderr = ktu.runShellCommand('{0}ssh {1} -o StrictHostKeyChecking=no {2}@{3} "{4}"'
                                                     .format(ssh_password_param, ssh_key_param, ssh_username, broker_host, cmd))
                except:
                    logger.error(traceback.print_exc())

                try:
                    #Force unmount shares
                    cmd = 'sudo umount -lf /share0 /share1 /share2 /share3 /share4'
                    stdout, stderr = ktu.runShellCommand('{0}ssh {1} -o StrictHostKeyChecking=no {2}@{3} "{4}"'
                                                         .format(ssh_password_param, ssh_key_param, ssh_username, broker_host, cmd))
                except:
                    logger.error(traceback.print_exc())

                #Remove entries from fstab so that mount cooridnator can write using new parameters
                cmd = 'sudo sed -i.bak \'/.file.core.windows.net/d\' /etc/fstab'
                stdout, stderr = ktu.runShellCommand('{0}ssh {1} -o StrictHostKeyChecking=no {2}@{3} "{4}"'
                                                     .format(ssh_password_param, ssh_key_param, ssh_username, broker_host, cmd))

                #Change attributes on local share dirs and remove them so that mount coordinator can create them again
                cmd = 'sudo chattr -R -i /share0 /share1 /share2 /share3 /share4'
                stdout, stderr = ktu.runShellCommand('{0}ssh {1} -o StrictHostKeyChecking=no {2}@{3} "{4}"'
                                                     .format(ssh_password_param, ssh_key_param, ssh_username, broker_host, cmd))

                cmd = 'sudo rm -rf /share0 /share1 /share2 /share3 /share4 /share5 '
                stdout, stderr = ktu.runShellCommand('{0}ssh {1} -o StrictHostKeyChecking=no {2}@{3} "{4}"'
                                                     .format(ssh_password_param, ssh_key_param, ssh_username, broker_host, cmd))

                #Remove Kafka init script
                cmd = 'sudo rm -f /etc/init.d/kafka'
                stdout, stderr = ktu.runShellCommand('{0}ssh {1} -o StrictHostKeyChecking=no {2}@{3} "{4}"'
                                                     .format(ssh_password_param, ssh_key_param, ssh_username, broker_host, cmd))

                #Install the new deb package
                cmd = 'sudo dpkg -i ~/*.deb'
                stdout, stderr = ktu.runShellCommand('{0}ssh {1} -o StrictHostKeyChecking=no {2}@{3} "{4}"'
                                                     .format(ssh_password_param, ssh_key_param, ssh_username, broker_host, cmd))

                #Copy the kafka jars and run Kafka mount coordinator
                cmd = 'sudo cp -f ~/kafka*.jar /usr/hdp/current/kafka-broker/libs/ ; sudo python /usr/lib/python2.7/dist-packages/hdinsight_kafka/kafka_mount_coordinator.py'
                stdout, stderr = ktu.runShellCommand('{0}ssh {1} -o StrictHostKeyChecking=no {2}@{3} "{4}"'
                                                     .format(ssh_password_param, ssh_key_param, ssh_username, broker_host, cmd))

                #Now start Ambari agent and Kafka
                cmd = 'sudo service ambari-agent start ; sudo kafka start'
                stdout, stderr = ktu.runShellCommand('{0}ssh {1} -o StrictHostKeyChecking=no {2}@{3} "{4}"'
                                                     .format(ssh_password_param, ssh_key_param, ssh_username, broker_host, cmd))
                logger.info('\nBroker host: {0} successfully patched\n==================================\n'.format(broker_host))
            except:
                logger.error(traceback.print_exc())
                errored_brokers.append(broker_host)
                #raise RuntimeError('failing due to execution error')
                logger.info('\nBroker host: {0} patching failed\n==================================\n'.format(broker_host))

    if len(errored_brokers) > 0:
        logger.info('Errored brokers: ' + str(len(errored_brokers)) + '\n' + reduce(lambda x, y : x + y, map(lambda b : b + '\n', errored_brokers)))

if __name__ == '__main__':
    ktu = KafkaTestUtils(logger, 'patchkafkadeb{0}'.format(int(time.time())) + '.log')
    main(ktu)
