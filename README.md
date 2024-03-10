# Genomics Annotation Service (GAS)

## Overview

The Genomics Annotation Service (GAS) is a capstone project designed to build a fully functional software-as-a-service platform for genomics annotation. This service leverages various cloud services running on Amazon Web Services (AWS) to provide a robust, scalable, and secure platform for genomic data processing and annotation.

Work flow diagram  

<img width="634" alt="Screen Shot 2024-03-10 at 3 13 49 PM" src="https://github.com/joy06261985/genomics-annotation-service/assets/77443634/4da210be-c80d-4041-ab45-6635cf348a9f">

Directory contents are as follows:
* `/web` - The GAS web app files
* `/ann` - Annotator files
* `/util` - Utility scripts/apps for notifications, archival, and restoration
* `/aws` - AWS user data files

## Key Features

- **User Authentication:** Users can log in via Globus Auth, with support for both Free and Premium user classes. Premium users have access to extended functionalities compared to Free users.
- **Job Submission:** Users can submit annotation jobs. Job size limitations apply based on the user's account type.
- **Upgrade Capability:** Free users can upgrade to a Premium account, enabling access to additional features and removing job size limitations.
- **Job Notifications:** Users receive email notifications upon the completion of their annotation jobs.
- **Data Browsing and Downloading:** Users can browse their submitted jobs and download annotation results. Access to data is managed based on the user's account type.

## System Components

- **Object Store:** Used for storing input files, annotated files, and job log files.
- **Key-Value Store:** Manages information on annotation jobs.
- **Relational Database:** Stores user account information.
- **Annotation Service:** A service that runs AnnTools for annotation.
- **Web Application:** Allows users to interact with the GAS through a web interface.
- **Message Queues and Notification Topics:** Coordinate system activities and user notifications.

## Technology Stack

- **Cloud Platform:** Amazon Web Services (AWS)
- **Compute:** AWS EC2 (Elastic Compute Cloud) for server instances
- **Storage:** 
  - S3 (Simple Storage Service) for object storage
  - Glacier for archival storage
  - DynamoDB for key-value data
  - RDS (Relational Database Service) for relational data
- **Web Server:** Flask framework (enhanced version for this project)
- **User Authentication:** Globus Auth
- **Frontend:** HTML, CSS (Bootstrap), JavaScript
- **Backend:** Python
- **Task Queues:** AWS SQS (Simple Queue Service)
- **Notification Service:** AWS SNS (Simple Notification Service)
- **Load Balancer:** AWS ELB (Elastic Load Balancer)
- **Auto Scaling:** AWS EC2 Auto Scaling
- **Security:** HTTPS, SSL/TLS
- **Monitoring:** AWS CloudWatch

## Web Framework

The project utilizes an enhanced version of the Flask framework for the web interface, offering styled web pages and a modular template structure for ease of development and user interaction.

## Security and Scalability

- The application enforces HTTPS for secure communication.
- Integration with Globus Auth provides a reliable and secure authentication mechanism.
- The backend architecture is designed for scalability, leveraging AWS services for load balancing and auto-scaling.



