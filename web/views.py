# views.py
#
# Copyright (C) 2015-2023 Vas Vasiliadis
# University of Chicago
#
# Application logic for the GAS
#
##
from flask_wtf.csrf import CSRFError
from auth import update_profile
import stripe
__author__ = "Vas Vasiliadis <vas@uchicago.edu>"

import uuid
import time
import json
from datetime import datetime, timezone, timedelta

import boto3
from botocore.client import Config
from boto3.dynamodb.conditions import Key, Attr, AttributeExists
from botocore.exceptions import BotoCoreError, ClientError, ParamValidationError

from flask import abort, flash, redirect, render_template, request, session, url_for, jsonify

from app import app, db
from decorators import authenticated, is_premium


"""general config"""
input_bucket = app.config["AWS_S3_INPUTS_BUCKET"]
result_bucket = app.config["AWS_S3_RESULTS_BUCKET"]
region = app.config["AWS_REGION_NAME"]
db_table = app.config['AWS_DYNAMODB_ANNOTATIONS_TABLE']
key_prefix = app.config["AWS_S3_KEY_PREFIX"]
expiration_time = app.config["AWS_SIGNED_REQUEST_EXPIRATION"]


"""general boto connection"""
# connect to s3
s3 = boto3.client(
        "s3",
        region_name=region,
        config=Config(signature_version="s3v4"),
    )
# connect to dynamodb
dynamodb = boto3.resource('dynamodb', region_name=region)
annotations_table = dynamodb.Table(db_table)
# connect to s3
sns = boto3.resource('sns', region_name=region)


"""Start annotation request
Create the required AWS S3 policy document and render a form for
uploading an annotation input file using the policy document

Note: You are welcome to use this code instead of your own
but you can replace the code below with your own if you prefer.
"""


@app.route("/annotate", methods=["GET"])
@authenticated
def annotate():

    user_id = session["primary_identity"]

    # Generate unique ID to be used as S3 key (name)
    key_name = (
        key_prefix
        + user_id
        + "/"
        + str(uuid.uuid4())
        + "~${filename}"
    )

    # Create the redirect URL
    redirect_url = str(request.url) + "/job"

    # Define policy conditions
    encryption = app.config["AWS_S3_ENCRYPTION"]
    acl = app.config["AWS_S3_ACL"]
    fields = {
        "success_action_redirect": redirect_url,
        "x-amz-server-side-encryption": encryption,
        "acl": acl,
        "csrf_token": app.config["SECRET_KEY"],
    }
    conditions = [
        ["starts-with", "$success_action_redirect", redirect_url],
        {"x-amz-server-side-encryption": encryption},
        {"acl": acl},
        ["starts-with", "$csrf_token", ""],
    ]

    # Generate the presigned POST call
    try:
        presigned_post = s3.generate_presigned_post(
            Bucket=input_bucket,
            Key=key_name,
            Fields=fields,
            Conditions=conditions,
            ExpiresIn=expiration_time,
        )
    except ClientError as e:
        app.logger.error(f"Unable to generate presigned URL for upload: {e}")
        return abort(500)

    # Render the upload form which will parse/submit the presigned POST
    return render_template(
        "annotate.html", s3_post=presigned_post, role=session["role"]
    )


"""Fires off an annotation job
Accepts the S3 redirect GET request, parses it to extract 
required info, saves a job item to the database, and then
publishes a notification for the annotator service.

Note: Update/replace the code below with your own from previous
homework assignments
"""


@app.route("/annotate/job", methods=["GET"])
def create_annotation_job_request():

    # Parse redirect URL query parameters for S3 object info
    bucket_name = request.args.get("bucket")
    s3_key = request.args.get("key")
    user_id = session["primary_identity"]

    # Extract the job ID from the S3 key
    job_id = s3_key.split('/')[2].split('~')[0]
    filename = s3_key.split('~')[1]

    # Persist job to database
    data = {
        "job_id": job_id,
        "user_id": user_id,
        "input_file_name": filename,
        "s3_inputs_bucket": bucket_name,
        "s3_key_input_file": s3_key,
        "submit_time": int(time.time()),
        "job_status": "PENDING"
    }
    try: 
        annotations_table.put_item(Item=data)
        print("data: ", data)
    except (BotoCoreError, ClientError, ParamValidationError) as e:
        return jsonify(code=500, message="Error putting item into DynamoDB: " + str(e))

    # Send message to request queue
    sns_topic_arn = app.config["AWS_SNS_JOB_REQUEST_TOPIC"]
    try:
        topic = sns.Topic(arn=sns_topic_arn)
        topic.publish(
            Message=json.dumps(data)
        )
        print("message sent")
    except (BotoCoreError, ClientError) as e:
        return jsonify(code=500, message="Error publishing SNS message: " + str(e))

    return render_template("annotate_confirm.html", job_id=job_id)


"""List all annotations for the user
"""


@app.route("/annotations", methods=["GET"])
@authenticated
def annotations_list():

    user_id = session["primary_identity"]

    try:
        # ref: query
        # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/dynamodb/client/query.html#
        response = annotations_table.query(
            IndexName='user_id_index',
            KeyConditionExpression=Key('user_id').eq(user_id)
        )
        print("completed query")
        jobs = response.get('Items', [])

        for job in jobs:
            # transform time formate
            # ref: datetime — Basic date and time types
            # https://docs.python.org/3/library/datetime.html
            submit_time_utc = datetime.fromtimestamp(
                int(job['submit_time']), tz=timezone.utc)
            submit_time_cst = submit_time_utc.astimezone(
                timezone(timedelta(hours=-6)))
            job['submit_time_cst'] = submit_time_cst.strftime(
                '%Y-%m-%d %H:%M:%S')
        print("jobs: ", jobs)

    except ClientError as e:
        app.logger.error(f"Error querying DynamoDB: {e}")
        # Use abort to handle unauthorized access with HTTP 500 error code
        abort(500)  

    # Check if no jobs were found and set a flag or pass an empty list
    no_jobs_found = len(jobs) == 0

    return render_template("annotations.html", annotations=jobs, no_jobs_found=no_jobs_found)


"""Display details of a specific annotation job
"""


@app.route("/annotations/<id>", methods=["GET"])
@authenticated
def annotation_details(id):

    user_id = session["primary_identity"]

    try:
        # Query the job using the job_id 
        # ref: get_item
        # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/dynamodb/table/get_item.html
        response = annotations_table.get_item(Key={'job_id': id})
        print("get response")
        job = response.get('Item', None)
        print("job: ", job)
        if job is None or job.get('user_id') != user_id:
            abort(403)

        # Convert the epoch time to a human-readable format
        job['submit_time'] = datetime.fromtimestamp(int(job['submit_time']), tz=timezone.utc).astimezone(
            timezone(timedelta(hours=-6))).strftime('%Y-%m-%d %H:%M:%S')
        if 'complete_time' in job:
            job['complete_time'] = datetime.fromtimestamp(int(job['complete_time']), tz=timezone.utc).astimezone(
                timezone(timedelta(hours=-6))).strftime('%Y-%m-%d %H:%M:%S')

    except ClientError as e:
        app.logger.error(f"Error retrieving job from DynamoDB: {e}")
        abort(500)

    return render_template("annotation.html", job=job)


"""Display the log file contents for an annotation job
"""


@app.route("/annotations/<id>/log", methods=["GET"])
@authenticated
def annotation_log(id):
    user_id = session["primary_identity"]

    try:
        response = annotations_table.get_item(Key={'job_id': id})
        job = response.get('Item', None)
        if job is None or job.get('user_id') != user_id:
            abort(403)

        log_file_key = job['s3_key_log_file']

        # Get the log file from S3
        # ref: get_object
        # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/s3/client/get_object.html
        log_file_object = s3.get_object(
            Bucket=result_bucket, Key=log_file_key)
        log_contents = log_file_object['Body'].read().decode('utf-8')

    except ClientError as e:
        app.logger.error(f"Error retrieving log file from S3: {e}")
        abort(500)

    # Pass the log file contents to the template
    return render_template("view_log.html", log_contents=log_contents, job_id=id)


"""Download input and results file
"""


@app.route("/download_input/<id>")
@authenticated
def download_input(id):
    user_id = session["primary_identity"]

    # get item from db
    response = annotations_table.get_item(Key={'job_id': id})
    job = response.get('Item', None)
    if job is None or job.get('user_id') != user_id:
        # The job does not exist or does not belong to the user
        abort(403)

    # This is the S3 key of the input file
    input_file_s3_key = job.get('s3_key_input_file')
    if not input_file_s3_key:
        # The S3 key was not found
        abort(404)

    # Generate a pre-signed URL for downloading the input file
    # ref: generate_presigned_url
    # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/s3/client/generate_presigned_url.html
    presigned_url = s3.generate_presigned_url('get_object',
                                                Params={'Bucket': input_bucket,
                                                        'Key': input_file_s3_key},
                                                ExpiresIn=expiration_time)
    return redirect(presigned_url)


@app.route("/download_results/<id>")
@authenticated
def download_results(id):
    user_id = session["primary_identity"]

    # get item from db
    response = annotations_table.get_item(Key={'job_id': id})
    job = response.get('Item', None)
    if job is None or job.get('user_id') != user_id:
        # The job does not exist or does not belong to the user
        abort(403)

    # This is the S3 key of the input file
    result_file_s3_key = job.get('s3_key_result_file')
    if not result_file_s3_key:
        # The S3 key was not found
        abort(404)

    # Generate a pre-signed URL for downloading the results file
    # ref: generate_presigned_url
    # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/s3/client/generate_presigned_url.html
    presigned_url = s3.generate_presigned_url('get_object',
                                                     Params={'Bucket': result_bucket,
                                                             'Key': result_file_s3_key},
                                                     ExpiresIn=expiration_time)
    return redirect(presigned_url)


"""Subscription management handler
"""


@app.route("/subscribe", methods=["GET", "POST"])
def subscribe():
    if request.method == "GET":
        # Display form to get subscriber credit card info
        return render_template("subscribe.html", stripe_public_key=app.config["STRIPE_PUBLIC_KEY"])

    elif request.method == "POST":
        try:
            # Process the subscription request
            stripe_token = request.form['stripe_token']
            print("stripe_token: ", stripe_token)
            email = session.get('email')
            if not stripe_token or not email:
                flash('Missing required information.', 'danger')
                return redirect(url_for('subscribe'))

            # Create a customer on Stripe
            # ref: Create a customer
            # https://docs.stripe.com/api/customers/create?lang=python
            stripe.api_key = app.config["STRIPE_SECRET_KEY"]
            customer = stripe.Customer.create(
                card=stripe_token,
                email=email,  
                name=session.get('name')     
            )
            print("customer: ", customer)

            # Subscribe customer to pricing plan
            # ref: Create a subscription
            # https://docs.stripe.com/api/subscriptions/create?gclid=COa3j-bOkZgCFRg6awodKWCXmQ%252F
            subscription = stripe.Subscription.create(
                customer=customer.id,
                items=[{'price': app.config["STRIPE_PRICE_ID"]}],  
            )
            print("subscription: ", subscription)

            
            user_id = session.get('primary_identity')
            if user_id:
                # Update user role in accounts database
                update_profile(identity_id=user_id, role="premium_user")
                # Update role in the session
                session['role'] = "premium_user"
                print("Updated user role to premium ")
            else:
                print("User session does not contain primary identity.")

            # Query DynamoDB for items with an 'results_file_archive_id'
            try:
                response = annotations_table.query(
                    IndexName='user_id_index',
                    KeyConditionExpression=Key('user_id').eq(user_id),
                    FilterExpression=Attr('results_file_archive_id').exists() & Attr('thaw_id').not_exists()
)
                items_with_archive_id = response.get('Items', [])

                archives_data = [
                    {
                        'job_id': item['job_id'],
                        'user_id': item['user_id'],
                        'results_file_archive_id': item['results_file_archive_id'],
                    }
                    for item in items_with_archive_id
                ]
                print("Archives Data:", archives_data)
            except ClientError as e:
                print(f"Error scanning DynamoDB for archive IDs: {str(e)}")
                archives_data = []

            # Send message to request queue
            data = {
                "archives_data": archives_data
            }
            sns_topic_arn_thaw = app.config["AWS_SNS_JOB_REQUEST_TOPIC_THAW"]
            try:
                topic = sns.Topic(arn=sns_topic_arn_thaw)
                topic.publish(
                    Message=json.dumps(data)
                )
                print("message sent")
            except (BotoCoreError, ClientError) as e:
                return jsonify(code=500, message="Error publishing SNS message: " + str(e))

            # Display confirmation page
            return render_template("subscribe_confirm.html", stripe_id=customer.id)
        
        # ref: Handling errors
        # https://docs.stripe.com/api/errors
        except stripe.error.CardError as e:
            body = e.json_body
            err = body.get('error', {})
            flash(f"Card error: {err.get('message')}", 'danger')

        except stripe.error.RateLimitError:
            flash('Too many requests made to the API too quickly.', 'danger')

        except stripe.error.InvalidRequestError:
            flash('Invalid parameters were supplied to Stripe API.', 'danger')

        except stripe.error.AuthenticationError:
            flash('Authentication with Stripe API failed.', 'danger')

        except stripe.error.APIConnectionError:
            flash('Network communication with Stripe failed.', 'danger')

        except stripe.error.StripeError:
            flash('Stripe error occurred. Please try again.', 'danger')

        except Exception as e:
            flash(str(e), 'danger')
            
        # Redirect back to the subscription page on error
        return redirect(url_for('subscribe'))



"""DO NOT CHANGE CODE BELOW THIS LINE
*******************************************************************************
"""

"""Set premium_user role
"""


@app.route("/make-me-premium", methods=["GET"])
@authenticated
def make_me_premium():
    # Hacky way to set the user's role to a premium user; simplifies testing
    update_profile(
        identity_id=session["primary_identity"], role="premium_user")
    return redirect(url_for("profile"))


"""Reset subscription
"""


@app.route("/unsubscribe", methods=["GET"])
@authenticated
def unsubscribe():
    # Hacky way to reset the user's role to a free user; simplifies testing
    update_profile(identity_id=session["primary_identity"], role="free_user")
    return redirect(url_for("profile"))


"""Home page
"""


@app.route("/", methods=["GET"])
def home():
    return render_template("home.html"), 200


"""Login page; send user to Globus Auth
"""


@app.route("/login", methods=["GET"])
def login():
    app.logger.info(f"Login attempted from IP {request.remote_addr}")
    # If user requested a specific page, save it session for redirect after auth
    if request.args.get("next"):
        session["next"] = request.args.get("next")
    return redirect(url_for("authcallback"))


"""404 error handler
"""


@app.errorhandler(404)
def page_not_found(e):
    return (
        render_template(
            "error.html",
            title="Page not found",
            alert_level="warning",
            message="The page you tried to reach does not exist. \
      Please check the URL and try again.",
        ),
        404,
    )


"""403 error handler
"""


@app.errorhandler(403)
def forbidden(e):
    return (
        render_template(
            "error.html",
            title="Not authorized",
            alert_level="danger",
            message="You are not authorized to access this page. \
      If you think you deserve to be granted access, please contact the \
      supreme leader of the mutating genome revolutionary party.",
        ),
        403,
    )


"""405 error handler
"""


@app.errorhandler(405)
def not_allowed(e):
    return (
        render_template(
            "error.html",
            title="Not allowed",
            alert_level="warning",
            message="You attempted an operation that's not allowed; \
      get your act together, hacker!",
        ),
        405,
    )


"""500 error handler
"""


@app.errorhandler(500)
def internal_error(error):
    return (
        render_template(
            "error.html",
            title="Server error",
            alert_level="danger",
            message="The server encountered an error and could \
      not process your request.",
        ),
        500,
    )


"""CSRF error handler
"""


@app.errorhandler(CSRFError)
def csrf_error(error):
    return (
        render_template(
            "error.html",
            title="CSRF error",
            alert_level="danger",
            message=f"Cross-Site Request Forgery error detected: {error.description}",
        ),
        400,
    )


# EOF
