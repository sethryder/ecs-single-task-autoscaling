import boto3, logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

ecs_client = boto3.client('ecs')

def lambda_handler(event, context):
    logger.info('Starting task count check')

    cluster_name = event['cluster_name']
    service_name = event['service_name']
    min_task_count = event['min_task_count']
    n_count = event['n_count']

    cluster = ecs_client.describe_clusters(clusters=[cluster_name])
    service = ecs_client.describe_services(cluster=cluster_name, services=[service_name])

    registeredContainerInstancesCount = cluster['clusters'][0]['registeredContainerInstancesCount']
    currentServiceDesiredTaskCount = service['services'][0]['desiredCount']
    newServiceDesiredTaskCount = registeredContainerInstancesCount - n_count

    if newServiceDesiredTaskCount < min_task_count:
        logger.info('Desired task count is below minimum task count, setting to minimum of %s', min_task_count)
        newServiceDesiredTaskCount = min_task_count

    if currentServiceDesiredTaskCount != newServiceDesiredTaskCount:
        logger.info('Current container instance count: %s', registeredContainerInstancesCount)
        logger.info('Current desired task count: %s', currentServiceDesiredTaskCount)
        logger.info('New desired task count to: %s', newServiceDesiredTaskCount)

        response = ecs_client.update_service(
            cluster=cluster_name,
            service=service_name,
            desiredCount=newServiceDesiredTaskCount,
        )
    else:
        logger.info('No action taken. Desired task is already correctly set at: %s', currentServiceDesiredTaskCount)

#event = {'cluster_name': 'magento-dev', 'service_name': 'stack-test', 'min_task_count': 3}
#lambda_handler(event, 'asdf')
