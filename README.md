# Genomics Annotation Service (GAS)

## Overview

The Genomics Annotation Service (GAS) is a capstone project designed to build a fully functional software-as-a-service platform for genomics annotation. This service leverages various cloud services running on Amazon Web Services (AWS) to provide a robust, scalable, and secure platform for genomic data processing and annotation.

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

## Web Framework

The project utilizes an enhanced version of the Flask framework for the web interface, offering styled web pages and a modular template structure for ease of development and user interaction.

## Security and Scalability

- The application enforces HTTPS for secure communication.
- Integration with Globus Auth provides a reliable and secure authentication mechanism.
- The backend architecture is designed for scalability, leveraging AWS services for load balancing and auto-scaling.



