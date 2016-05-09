import boto3, logging, json

elb_client = boto3.client('elb')
ecs_client = boto3.client('ecs')
sqs_client = boto3.client('sqs')

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    logger.info('Staring ECS deregister function')
    logger.info('Raw event information: {}'.format(event))

    lifecycle_queue_name = event['lifecycle_queue_name']
    elb_monitor_queue_name = event['elb_monitor_queue_name']
    elb_name = event['elb_name']
    cluster_name = event['cluster_name']

    #setup sqs
    logger.info('Getting queue URL for %s', lifecycle_queue_name)
    response = sqs_client.create_queue(QueueName=lifecycle_queue_name)
    lifecycle_queue_url = response['QueueUrl']

    logger.info('Getting queue URL for %s', elb_monitor_queue_name)
    response = sqs_client.create_queue(QueueName=elb_monitor_queue_name)
    elb_monitor_queue_url = response['QueueUrl']

    #get the message
    logger.info('Checking for pending terminations')
    queue_message = sqs_client.receive_message(QueueUrl=lifecycle_queue_url,MaxNumberOfMessages=1)

    if queue_message.get('Messages'):
        logger.info('Pending deregister found')
        decoded_message = json.loads(queue_message['Messages'][0]['Body'])
        receipt_handle = queue_message['Messages'][0]['ReceiptHandle']

        instance_id = decoded_message['EC2InstanceId']
        auto_scaling_group = decoded_message['AutoScalingGroupName']
        life_cycle_hook_name = decoded_message['LifecycleHookName']
        lifecycle_action_token = decoded_message['LifecycleActionToken']

        logger.info('Starting termination process for instance: %s', instance_id)

        #first we deregister the instance, this will NOT kill any running tasks.
        response = ecs_client.list_container_instances(
            cluster=cluster_name,
            maxResults=100
        )

        logger.info('Searcing for instance %s\'s ARN', instance_id)

        terminating_instance_arn = None
        for instance_arn in response['containerInstanceArns']:
            instance_response = ecs_client.describe_container_instances(
                cluster=cluster_name,
                containerInstances=[instance_arn]
            )
            i_instance_id = instance_response['containerInstances'][0]['ec2InstanceId']
            if i_instance_id == instance_id:
                terminating_instance_arn = instance_arn

        if terminating_instance_arn is None:
            logger.error('Could not find ECS ARN for instance: %s', instance_id)
        else:
            logger.info('Found ARN, deregistering conatainer instance ARN: %s', instance_arn)
            response = ecs_client.deregister_container_instance(
                cluster=cluster_name,
                containerInstance=terminating_instance_arn,
                force=True
            )

        #TODO: Check to see if the instance is actually behind the ELB,
        #if not possibly just terminate it here, save us some time.

        #remove instance from ELB
        logger.info('Removing instance %s from ELB', instance_id)
        response = elb_client.deregister_instances_from_load_balancer(
            LoadBalancerName=elb_name,
            Instances=[{'InstanceId': instance_id},]
        )

        #tell our elb monitoring lamba function about the instance
        queue_message = {
            'elb_name': elb_name,
            'instance_id': instance_id,
            'auto_scaling_group': auto_scaling_group,
            'life_cycle_hook_name': life_cycle_hook_name,
            'lifecycle_action_token': lifecycle_action_token
        }
        logger.info('Queuing message for ELB monitoring and final termination for instance: %s', instance_id)
        queue_json_message = json.dumps(queue_message)
        response = sqs_client.send_message(QueueUrl=elb_monitor_queue_url, MessageBody=queue_json_message)

        #now that we are finished delete the message
        logger.info('Deregistration complete, Removing message from queue with handle: %s', receipt_handle)
        response = sqs_client.delete_message(QueueUrl=lifecycle_queue_url, ReceiptHandle=receipt_handle)
    else:
        logger.info('No pending terminations')

    logger.info('ECS deregister function finished')

event = {
    'lifecycle_queue_name': 'magento-dev-ecs-autoscale',
    'elb_monitor_queue_name': 'ecs-autoscale-termination-monitor',
    'elb_name': 'ecom-s-ext-lb-1',
    'cluster_name': 'magento-dev',
    }

lambda_handler(event, 'asdf')
