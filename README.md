# GAS Framework
An enhanced web framework (based on [Flask](https://flask.palletsprojects.com/)) for use in the capstone project. Adds robust user authentication (via [Globus Auth](https://docs.globus.org/api/auth)), modular templates, and some simple styling based on [Bootstrap](https://getbootstrap.com/docs/3.3/).

Directory contents are as follows:
* `/web` - The GAS web app files
* `/ann` - Annotator files
* `/util` - Utility scripts/apps for notifications, archival, and restoration
* `/aws` - AWS user data files

IMPORTANT: My Annotator web server running at http://chenhui1-a13-ann.ucmpcs.org:5000 not port 4433.  

A16 update   
 
* `/web/templates/annotation.html` : added conditions to display the restored information   
* `/web/views.py` : modified /subscribe endpoint.  
* `/web/config.py` : updated sns information  
* `/util/thaw/thaw_script.py` : file that initiate the thaw job  
* `/util/thaw/thaw_script_config.py` : config file for thaw_script.py  
* `/util/thaw/run_thaw_script.sh` : debug a path issue /  
* `/util/restore/restore.py` : the lambda function, restore job  
  

Initially, my exploration began with thaw_app.py, attracted by its event-driven design that promised a more streamlined and efficient way to process messages from SNS. This approach, theoretically, should offer enhanced performance by avoiding constant polling. However, this efficiency comes at a cost: a dependency on a reliable internet connection. I encountered significant challenges during periods of weak connectivity, which undermined the stability of the system.

In response to these challenges, I pivoted to thaw_script.py. This script, while seemingly less sophisticated due to its reliance on continuous polling, demonstrated remarkable reliability and simplicity in implementation. Unlike thaw_app.py, which necessitates a complex setup involving both SNS and SQS for message capturing and requeuing, thaw_script.py operates with a singular SQS queue. This simplifies the architecture by directly managing message receipt and deletion, reducing potential confusion and complexity.

From a reliability and availability standpoint, thaw_script.py stands out, especially in environments with fluctuating internet quality. Its polling mechanism diligently attempts to process messages, ensuring critical operations aren't missed due to temporary network disruptions. This straightforward approach, though less elegant, offers a robust solution by minimizing complexity and potential failure points inherent in managing multiple services as seen in the thaw_app.py setup.

Conversely, thaw_app.py embodies modern architectural ideals, emphasizing scalability and operational efficiency through an event-driven model. By leveraging Flask app endpoints to initiate actions upon receiving job notifications, it eliminates the inefficiencies associated with constant message checking. This model is poised for better scalability and faster response times, albeit heavily reliant on stable network conditions and a more intricate configuration to maintain message integrity and processing reliability.

While thaw_script.py may lack the architectural sophistication of thaw_app.py, it offers compensatory benefits in simplicity and dependability, particularly under unstable network conditions. This practicality ensures uninterrupted critical operations, illustrating the trade-offs between consistency, availability, and complexity in architectural decision-making. Our choice leans towards reliability and straightforwardness, prioritizing operational continuity over theoretical efficiency in connectivity-challenged scenarios.

Further enhancing the workflow, after successful subscription, the views.py endpoint sends a list of archive IDs to thaw through SNS topic publishing. To enhance efficiency, I utilized query operations instead of scan to retrieve data lists by archive ID. In the thaw job process, to safeguard against message loss or job failure, I integrated SQS for initial message reception, processed subsequently by thaw_script.py. Initially, I experimented with an expedited thaw job but transitioned to a standard version for graceful degradation upon failure.

To incorporate querying in Lambda, I included the user ID in the Job Description, along with an SNSTopic for notification triggering once the thaw object was ready for restoration. Unlike the previous assignment's approach(put sqs receiver in the endpoints), I now use SQS as an intermediary between SNS and Lambda, facilitating message reception and triggering the Lambda function for restoration. This setup retains failed job messages in the queue, maintaining them in 'in-flight' status for efficient debugging and redeployment.

Ultimately, I updated thaw_status and thaw_type in DynamoDB, enhancing the front-end display with more detailed information for users to check and download their restored result files. This refinement ensures a more user-friendly and reliable system, emphasizing robustness and clarity in the data restoration process.
