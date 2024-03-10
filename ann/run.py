# run.py
#
# Runs the AnnTools pipeline
#
# NOTE: This file lives on the AnnTools instance and
# replaces the default AnnTools run.py
#
# Copyright (C) 2015-2024 Vas Vasiliadis
# University of Chicago
##
__author__ = "Vas Vasiliadis <vas@uchicago.edu>"

import sys
import time
import driver
import os
import shutil
import boto3
from botocore.client import Config
from botocore.exceptions import BotoCoreError, ClientError
import json

# Get configuration
from configparser import ConfigParser, ExtendedInterpolation

config = ConfigParser(os.environ, interpolation=ExtendedInterpolation())
config.read("/home/ubuntu/gas/ann/annotator_config.ini")

region = config.get('aws', 'AwsRegionName')
db_table = config.get('gas', 'AnnotationsTable')
bucket = config.get('s3', 'ResultsBucketName')
keyPrefix = config.get('s3', 'KeyPrefix')
CnetId = config.get('DEFAULT', 'CnetId')
sns_topic_arn = config.get('sqs', 'SnsTopicArn')


# general static connection to boto3
# connect to s3
s3 = boto3.client('s3', region_name=region,
                config=Config(signature_version='s3v4'))
# connect to db
dynamodb = boto3.resource('dynamodb', region_name=region)
annotations_table = dynamodb.Table(db_table)
# connect to sqs
sns = boto3.resource('sns', region_name=region)

"""A rudimentary timer for coarse-grained profiling
"""


class Timer(object):
    def __init__(self, verbose=True):
        self.verbose = verbose

    def __enter__(self):
        self.start = time.time()
        return self

    def __exit__(self, *args):
        self.end = time.time()
        self.secs = self.end - self.start
        if self.verbose:
            print(f"Approximate runtime: {self.secs:.2f} seconds")


def main():

    # Get job parameters
    input_file_name = sys.argv[1]
    job_id = sys.argv[2]
    user_id = sys.argv[3]
    filename = sys.argv[4].split('.')[0]

    # Run the AnnTools pipeline
    with Timer():
        driver.run(input_file_name, "vcf")

    success = True 
    # 1. Upload the results file to S3 results bucket
    try:
        results_file = f'/home/ubuntu/gas/ann/outputs/{job_id}/{filename}.annot.vcf'
        s3.upload_file(results_file, bucket,
                       f'{keyPrefix}{user_id}/{job_id}~{filename}.annot.vcf')
        
    except (BotoCoreError, ClientError) as e:
        print(f"Error uploading {results_file} to S3 {bucket} bucket: {e}")
        success = False

    # 2. Upload the log file to S3 results bucket
    try:
        log_file = f'/home/ubuntu/gas/ann/outputs/{job_id}/{filename}.vcf.count.log'
        s3.upload_file(log_file, bucket,
                       f'{keyPrefix}{user_id}/{job_id}~{filename}.vcf.count.log')
        print("Files uploaded to S3")
    except (BotoCoreError, ClientError) as e:
        print(f"Error uploading {log_file} to S3 {bucket} bucket: {e}")
        success = False

    # 3. Update DynamoDB item
    try:
        # Update the job item in DynamoDB
        complete_time = int(time.time())
        result_file = f'{keyPrefix}{user_id}/{job_id}~{filename}.annot.vcf'
        annotations_table.update_item(
            Key={'job_id': job_id},
            UpdateExpression='SET s3_results_bucket = :results_bucket, s3_key_result_file = :result_file, '
            's3_key_log_file = :log_file, complete_time = :complete_time, '
            'job_status = :status',
            ExpressionAttributeValues={
                ':results_bucket': bucket,
                ':result_file': result_file,
                ':log_file': f'{keyPrefix}{user_id}/{job_id}~{filename}.vcf.count.log',
                ':complete_time': complete_time,
                ':status': 'COMPLETED'
            }
        )
        print("DynamoDB item updated")
    except (BotoCoreError, ClientError) as e:
        print(f"Error updating DynamoDB item: {str(e)}")
        success = False

    # 5. publishes a notification to the chenhui1_a12_job_results topic 
    if success:
        job_url = f'https://{CnetId}-a16-web.ucmpcs.org:4433/annotations/{job_id}/log'
        # new inserted data result file for A14 archive_app.py
        data = {
            "job_id": job_id,
            "user_id": user_id, # A14 new inserted
            "complete_time": complete_time,
            "link": job_url,
            "result_file": result_file # A14 new inserted
        }
        # Send message to request queue
        topic = sns.Topic(arn=sns_topic_arn)
        topic.publish(
            Message=json.dumps(data)
        )
        print("message sent")
    
    # 4. Clean up (delete) local job files
    try:
        folder_path = f"/home/ubuntu/gas/ann/outputs/{job_id}"
        shutil.rmtree(folder_path)
        print("Local files deleted")
    except OSError as e:
        print(f"Error deleting {folder_path}: {e}")

    


if __name__ == "__main__":
    main()

# EOF
