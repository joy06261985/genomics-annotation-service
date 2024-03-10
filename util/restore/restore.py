# restore.py
#
# Restores thawed data, saving objects to S3 results bucket
# NOTE: This code is for an AWS Lambda function
#
# Copyright (C) 2015-2023 Vas Vasiliadis
# University of Chicago
##


import boto3
import json
from botocore.exceptions import ClientError
from botocore.client import Config
from boto3.dynamodb.conditions import Key, Attr


region = "us-east-1"
s3_bucket_name = "gas-results"
db_table = "chenhui1_annotations"
vault = "ucmpcs"

# AWS connection
glacier_client = boto3.client('glacier', region_name=region)
s3 = boto3.client('s3', region_name=region, config=Config(signature_version='s3v4'))
dynamodb = boto3.resource('dynamodb', region_name=region)
annotations_table = dynamodb.Table(db_table)


def lambda_handler(event, context):
    print("event: ", event)
    record_body = json.loads(event['Records'][0]['body'])
    sns_message = json.loads(record_body['Message'])
    archive_id = sns_message['ArchiveId']
    user_id = sns_message['JobDescription']

    try:
        response = annotations_table.query(
            IndexName='user_id_index',  
            KeyConditionExpression=Key('user_id').eq(user_id),  
            FilterExpression=Attr('results_file_archive_id').eq(archive_id)
        )
        
        items = response.get('Items', [])
        if not items:
            print(f"No DynamoDB record found for thaw_id: {archive_id}")
            return {
                'statusCode': 404,
                'body': json.dumps(f"No record found for thaw_id: {archive_id}")
            }
        print("Retrieve the corresponding DynamoDB record: ", items)
        record = items[0]
        
        # Extract data from the record
        job_id = record['job_id']
        thaw_id = record['thaw_id']
        s3_key_result_file = record['s3_key_result_file']

        # Check if the Glacier job has finished and the file is ready to be copied
        # ref: describe_job
        # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/glacier/client/describe_job.html
        job_status = glacier_client.describe_job(vaultName=vault, jobId=thaw_id)['StatusCode']
        print("get thaw job status: ", job_status)
        if job_status != 'Succeeded':
            print(f"Glacier job {thaw_id} is not ready. Status: {job_status}")
            return {'statusCode': 202, 'body': json.dumps(f"Glacier job {thaw_id} is not ready. Status: {job_status}")}

        # Get the output of the Glacier job
        # ref: get_job_output
        # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/glacier/client/get_job_output.html
        try:
            job_output = glacier_client.get_job_output(vaultName=vault, jobId=thaw_id)
            temp_data = job_output['body'].read()
            print("get temp thawed output: ", temp_data)
        except ClientError as e:
            print(f"Error getting job output from Glacier: {e}")
            return {'statusCode': 500, 'body': json.dumps('Error getting job output from Glacier.')}


        # upload this data to the S3 bucket
        # ref: put_object
        # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/s3/client/put_object.html
        try:
            s3.put_object(Bucket=s3_bucket_name, Key=s3_key_result_file, Body=temp_data)
            print("put object to s3 result bucket")
        except ClientError as e:
            print(f"Error putting object to S3: {e}")
            return {'statusCode': 500, 'body': json.dumps('Error putting object to S3.')}


        # Delete the archive from Glacier after successful copy
        # ref: delete_archive
        # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/glacier/client/delete_archive.html
        try:
            glacier_client.delete_archive(vaultName=vault, archiveId=archive_id)
            print("delete archive object")
        except ClientError as e:
            print(f"Error deleting archive from Glacier: {e}")
            return {'statusCode': 500, 'body': json.dumps('Error deleting archive from Glacier.')}

        # Update DynamoDB to reflect that the object has been restored and the archive deleted
        try: 
            annotations_table.update_item(
                Key={'job_id': job_id},
                UpdateExpression='SET thaw_status = :statusVal',
                ExpressionAttributeValues={
                    ':statusVal': 'COMPLETED'}
            )
            print("updated thaw status to dynamodb")
            return {
                'statusCode': 200,
                'body': json.dumps('Thawed object has been restored and archive deleted.')
            }
        except ClientError as e:
            print(f"Error updating DynamoDB: {e}")
            return {'statusCode': 500, 'body': json.dumps('An error occurred during the updating process.')}
        

    except ClientError as e:
        print(f"An error occurred: {e}")
        return {
            'statusCode': 500,
            'body': json.dumps('An error occurred during the restore process.')
        }


