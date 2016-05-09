# Single Task ECS Autoscaling

These lambda functions are built to help making scaling a (single task) ECS Cluster a bit easier and manageble.

## Setup
We will walk through explaining what each function does and how to setup the functions for your cluster.

### ecs_lambda_austoscale_task.py
This is a small function that has one simple task. Keep your cluster at N+1 (or whatever you configure). Meaning it will make sure that there is always one (or more) instances then there is tasks. This function will not scale up or down any instances, its primary task is to.. well manage running tasks.

##### Setup
1. Create a new Lamba functon (we will name it **ecsLambdaAutoScale** in our example) but you can name it what you want.
2. Create a Cloudwatch event (using Rules) that will run the function every minute.
  1. You can see the [Cloudwatch Docs](http://docs.aws.amazon.com/AmazonCloudWatch/latest/DeveloperGuide/WhatIsCloudWatchEvents.html) for creating the event.
  2. To set the config options, use **Configure Input** and select **Constant (JSON text)**.
  3. Use the following JSON to set your options, replacing with your actual cluster information and configuring the way you would like:
```
{
    "cluster_name": "cluster-name",
    "service_name": "service-name",
    "min_task_count": 2,
    "n_count": 1
}
```

It should now be running properly. You can check Cloudwatch Logs for the functions output.

##### Sample Log Output:
```
[INFO]	2016-05-09T14:51:15.999Z	9b2cd6e3-15c5-15e8-8312-7667ba85644d	Starting task count check
[INFO]	2016-05-09T14:51:16.114Z	9b2cd6e3-15c5-15e8-8312-7667ba85644d	No action taken. Desired task is already correctly set at: 4
END RequestId: 9b2cd6e3-15c5-15e8-8312-7667ba85644d
```

### Autoscaling Group
For the next two functions you are going to need a functioning autoscaling group.

The basic setup is outside the scope of this documentation. You can see AWS docs on how to setup an Autoscaling Group [here](http://docs.aws.amazon.com/autoscaling/latest/userguide/GettingStartedTutorial.html).

### Lifecycle Hook

We need to setup a termination lifecycle hook for the Autoscaling Group. This will make Autoscaling mark an instance for termination and now actually terminate the instance until we give it the OK. This will let our other two functions properly deregister and remove the instance from the Elastic Load Balancer.

##### Setup



### ecs_lambda_deregister_instance.py

### ecs_lambda_terminate_instance.py
