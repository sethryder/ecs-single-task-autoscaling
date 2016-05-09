import boto3, logging, json, sys

logger = logging.getLogger()
logger.setLevel(logging.INFO)

elb_client = boto3.client('elb')
sqs_client = boto3.client('sqs')
asg_client = boto3.client('autoscaling')

def lambda_handler(event, context):
    logger.info('Staring ECS terminate function')
    logger.info('got event{}'.format(event))

    queue_name = event['queue_name']

    response = sqs_client.create_queue(QueueName=queue_name)
    lifecycle_queue_url = response['QueueUrl']

    queue_message = sqs_client.receive_message(QueueUrl=lifecycle_queue_url,MaxNumberOfMessages=1)

    logger.info('Checking for instances pending termination')
    if queue_message.get('Messages'):
        logger.info('Pending termination found')
        decoded_message = json.loads(queue_message['Messages'][0]['Body'])
        receipt_handle = queue_message['Messages'][0]['ReceiptHandle']

        instance_id = decoded_message['instance_id']
        auto_scaling_group = decoded_message['auto_scaling_group']
        elb_name = decoded_message['elb_name']
        lifecycle_action_token = decoded_message['lifecycle_action_token']
        life_cycle_hook_name = decoded_message['life_cycle_hook_name']

        logger.info('Performing lifecycle check for instance: %s', instance_id)

        logger.info('Checking if instance is still present in the ELB: %s', elb_name)
        elb_response = elb_client.describe_load_balancers(LoadBalancerNames=[elb_name])

        instance_present = False
        for elb in elb_response['LoadBalancerDescriptions'][0]['Instances']:
            if elb['InstanceId'] == instance_id:
                instance_present = True

        if instance_present == False:
            logger.info('Instance not found in ELB, setting Lifecycle result to "CONTINUE" for: %s', instance_id)
            response = asg_client.complete_lifecycle_action(
                LifecycleHookName=life_cycle_hook_name,
                AutoScalingGroupName=auto_scaling_group,
                LifecycleActionToken=lifecycle_action_token,
                LifecycleActionResult='CONTINUE',
            )

            logger.info('Removing message from queue: %s', receipt_handle)
            response = sqs_client.delete_message(QueueUrl=lifecycle_queue_url, ReceiptHandle=receipt_handle)
        else:
            logger.info('Instance is still in the ELB, attempting another deregister')
            #remove instance from ELB
            logger.info('Removing instance %s from ELB', instance_id)
            response = elb_client.deregister_instances_from_load_balancer(
                LoadBalancerName=elb_name,
                Instances=[{'InstanceId': instance_id},]
            )
    else:
        logger.info('No pending terminations found')

    logger.info('ECS terminate function finished')

event = {"queue_name":"ecs-autoscale-termination-monitor"}
lambda_handler(event, 'asdf')
