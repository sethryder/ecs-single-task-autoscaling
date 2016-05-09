# Single Task ECS Autoscaling

These lambda functions are built to help making scaling a (single task) ECS Cluster a bit easier and manageable.

**Note**: This is some early code. It has been used in production as of yet, so use at your own risk. I am sure it can be improved in many ways
but I wanted to get it out.

## Setup
We will walk through explaining what each function does and how to setup the functions and other parts (IAM, Autoscaling Groups, etc) of the cluster.

### IAM Role/Policy

The first step is to setup IAM roles and policies that the Lambda functions and other parts of the process can use.

First lets create a policy for the Lambda Functions.

1. Create a new Policy, we will use the name **LambdaECSScalingExecutionRole** in this example.
2. Select **Create Your Own Policy**.
3. Enter a name and description for the policy.
4. You can paste in the following policy. **Please note**: This policy is pretty wide open, so you can adjust it to make it more secure/controlled.
```
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "logs:CreateLogGroup",
                "logs:CreateLogStream",
                "logs:PutLogEvents",
                "ecs:DescribeClusters",
                "ecs:DescribeContainerInstances",
                "ecs:DescribeServices",
                "ecs:DescribeTaskDefinition",
                "ecs:DescribeTask",
                "ecs:UpdateService",
                "elasticloadbalancing:DeregisterInstancesFromLoadBalancer",
                "elasticloadbalancing:DescribeLoadBalancers",
                "autoscaling:CompleteLifecycleAction",
                "sqs:CreateQueue",
                "sqs:GetQueueUrl",
                "sqs:SendMessage",
                "sqs:ReceiveMessage",
                "sqs:ChangeMessageVisibility",
                "sqs:DeleteMessage"
            ],
            "Resource": "*"
        }
    ]
}
```

Then lets create the role:

1. Create a new role, we will use the name **lambda_autoscale_ecs** in the example
2. For the role type, select **AWS Lambda** under **AWS Service Roles**.
3. Attach the policy we just created above, you can search for it by name.
4. Click **Create Role**

We need to create one more role. This will be used by the Autoscaling Group to notify SQS that a termination is pending.

1. Create a new role, we will us the name **AutoScalingNotification**
2. For the role type, select **AutoScaling Notification Access** under **AWS Service Roles**.
3. Attach the policy **AmazonSQSFullAccess**. **Please note**: This policy again is very wide open. You can create a much more narrow policy for what you need.
4. Click **Create Role**
5. Note the ARN for this newly created role as it will be used in a future step.

We are now all set with our IAM Policies and Roles.

### Autoscaling Group
Autoscaling will take care of scaling our cluster up and notifying us when we need to scale down.

##### Autoscaling Group Setup

The basic setup is outside the scope of this documentation. You can see AWS docs on how to setup an Autoscaling Group [here](http://docs.aws.amazon.com/autoscaling/latest/userguide/GettingStartedTutorial.html).

##### Lifecycle Hook Setup

We need to setup a termination lifecycle hook for the Autoscaling Group. This will make Autoscaling mark an instance for termination and now actually terminate the instance until we give it the OK. This will let our other two functions properly deregister and remove the instance from the Elastic Load Balancer.

Note: We will be using the [AWS CLI](http://docs.aws.amazon.com/cli/latest/userguide/cli-chap-getting-set-up.html) to set this up.

We will be using a SQS queues for passing messages between functions. You will need to create two queues. One will be where the Lifecycle Hook posts messages when it wants to terminate an instance. The other will be where it stores servers that have been deregistered and are awaiting termination. When creating these queues note the ARN.

We will use the two following queues:

1. test-cluster-ecs-autoscale (this is where the Lifecycle Hook will put pending instances)
2. ecs-autoscale-termination-monitor (this is where our deregister script will put instances that are pending termination)

Now lets setup the Lifecycle Hook:

```
aws autoscaling put-lifecycle-hook --lifecycle-hook-name ecsTermination --auto-scaling-group-name magento-dev-ecs-cluster --lifecycle-transition autoscaling:EC2_INSTANCE_TERMINATING --notification-target-arn SQS_QUEUE --role-arn IAM_ASG_NOTIFICATION_ROLE
```

Replacing **SQS_QUEUE** with the queue you made above (**test-cluster-ecs-autoscale** in the example) and **IAM_ASG_NOTIFICATION_ROLE** you made.

The lifecycle hook is now setup and ready to go. Any downscaling event will create an event and place it in first SQS queue we created.

### ecs_lambda_austoscale_task.py
This is a small function that has one simple task. Keep your cluster at N+1 (or whatever you configure). Meaning it will make sure that there is always one (or more) instances then there is tasks. This function will not scale up or down any instances, its primary task is to.. well manage running tasks.

##### Setup
1. Create a new Lambda function (we will name it **ecsLambdaAutoScale** in our example) but you can name it what you want.
2. Attach the **lambda_autoscale_ecs** role to the function.
3. Create a CloudWatch event (using Rules) that will run the function every minute.
  1. You can see the [CloudWatch Docs](http://docs.aws.amazon.com/AmazonCloudWatch/latest/DeveloperGuide/WhatIsCloudWatchEvents.html) for creating the event.
  2. To set the config options, use **Configure Input** and select **Constant (JSON text)**.
  3. Use the following JSON to set your options, replacing with your actual cluster information and configuring the way you would like:
```
{
    "cluster_name": "cluster-name",
    "service_name": "ecs-autoscale-termination-monitor",
    "min_task_count": 2,
    "n_count": 1
}
```

It should now be running properly. It is set to log to CloudWatch, so you can check the CloudWatch Logs for output.

##### Sample Log Output:
```
START RequestId: 9b2cd6e3-15c5-15e8-8312-7667ba85644d Version: $LATEST
[INFO]	2016-05-09T14:51:15.999Z	9b2cd6e3-15c5-15e8-8312-7667ba85644d	Starting task count check
[INFO]	2016-05-09T14:51:16.114Z	9b2cd6e3-15c5-15e8-8312-7667ba85644d	No action taken. Desired task is already correctly set at: 4
END RequestId: 9b2cd6e3-15c5-15e8-8312-7667ba85644d
```

### ecs_lambda_deregister_instance.py

This function checks our SQS queue to see if any instances are pending notification. If it does find an instance pending termination it takes the proper steps to safetly decommision the instance. This includes unregistering it from our ECS cluster, removing it from the ELB (allowing proper connection draining). Once it has done these functions it will add the instance to the termination monitoring pool where the **ecs_lambda_terminate_instance.py** function will complete termination.

##### Setup
1. Create a new Lambda functon (we will name it **ecsLambdaDeregisterInstance** in our example) but you can name it what you want.
2. Attach the **lambda_autoscale_ecs** role to the function.
2. Create a CloudWatch event (using Rules) that will run the function every minute.
  1. You can see the [CloudWatch Docs](http://docs.aws.amazon.com/AmazonCloudWatch/latest/DeveloperGuide/WhatIsCloudWatchEvents.html) for creating the event.
  2. To set the config options, use **Configure Input** and select **Constant (JSON text)**.
  3. Use the following JSON to set your options, replacing with your actual cluster information (including the ELB that is in front of the service).:
```
{
    'lifecycle_queue_name': 'test-cluster-ecs-autoscale',
    'elb_monitor_queue_name': 'ecs-autoscale-termination-monitor',
    'elb_name': 'test-cluster-elb',
    'cluster_name': 'test-cluster'
}
```

##### Sample Log Output:
```
START RequestId: ec732b46-16c8-1ae6-a58f-6384156e777c Version: $LATEST
[INFO]	2016-05-09T17:09:59.653Z	ec732b46-16c8-1ae6-a58f-6384156e777c	Staring ECS deregister function
[INFO]	2016-05-09T17:09:59.653Z	ec732b46-16c8-1ae6-a58f-6384156e777c	Raw event information: {u'elb_monitor_queue_name': u'ecs-autoscale-termination-monitor', u'cluster_name': u'test-cluster', u'lifecycle_queue_name': u'test-cluster-ecs-autoscale', u'elb_name': u'test-cluster-elb'}
[INFO]	2016-05-09T17:09:59.653Z	ec732b46-16c8-1ae6-a58f-6384156e777c	Getting queue URL for test-cluster-ecs-autoscale
[INFO]	2016-05-09T17:09:59.658Z	ec732b46-16c8-1ae6-a58f-6384156e777c	Starting new HTTPS connection (1): queue.amazonaws.com
[INFO]	2016-05-09T17:09:59.866Z	ec732b46-16c8-1ae6-a58f-6384156e777c	Getting queue URL for ecs-autoscale-termination-monitor
[INFO]	2016-05-09T17:09:59.883Z	ec732b46-16c8-1ae6-a58f-6384156e777c	Checking for pending terminations
[INFO]	2016-05-09T17:09:59.946Z	ec732b46-16c8-1ae6-a58f-6384156e777c	No pending terminations
[INFO]	2016-05-09T17:09:59.946Z	ec732b46-16c8-1ae6-a58f-6384156e777c	ECS deregister function finished
END RequestId: dc762b46-1608-11e6-a58f-6346156e877c
```

### ecs_lambda_terminate_instance.py

This function checks the termination queue for instances that are ready to be terminated. Before sending the OK for termination it will check to make sure the instance has successfully been deregistered from the ELB. Once it determines that it is no longer registered to the ELB it will tell the Autoscaling Group that it is OK to terminate the instance.

##### Setup
1. Create a new Lambda function (we will name it **ecsLambdaTerminateInstance** in our example) but you can name it what you want.
2. Attach the **lambda_autoscale_ecs** role to the function.
2. Create a CloudWatch event (using Rules) that will run the function every minute.
  1. You can see the [CloudWatch Docs](http://docs.aws.amazon.com/AmazonCloudWatch/latest/DeveloperGuide/WhatIsCloudWatchEvents.html) for creating the event.
  2. To set the config options, use **Configure Input** and select **Constant (JSON text)**.
  3. Use the following JSON to set your options, replacing with your actual cluster information (including the ELB that is in front of the service).:
```
{"queue_name": "ecs-autoscale-termination-monitor"}
```

##### Sample Log Output:
```
START RequestId: 3c626ed1-1605-11e6-91a1-9f2f3ab8eff3 Version: $LATEST
[INFO]	2016-05-09T16:44:02.591Z	3c626ed1-1605-11e6-91a1-9f2f3ab8eff3	Staring ECS terminate function
[INFO]	2016-05-09T16:44:02.591Z	3c626ed1-1605-11e6-91a1-9f2f3ab8eff3	got event{u'queue_name': u'ecs-autoscale-termination-monitor'}
[INFO]	2016-05-09T16:44:02.679Z	3c626ed1-1605-11e6-91a1-9f2f3ab8eff3	Checking for instances pending termination
[INFO]	2016-05-09T16:44:02.679Z	3c626ed1-1605-11e6-91a1-9f2f3ab8eff3	No pending terminations found
[INFO]	2016-05-09T16:44:02.679Z	3c626ed1-1605-11e6-91a1-9f2f3ab8eff3	ECS terminate function finished
END RequestId: 3c626ed1-1605-11e6-91a1-9f2f3ab8eff3
```
