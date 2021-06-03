# **Providing Feedback to Subjects**
Ideally we would like to provide feedback to the subject in the MRI scanner via a web interface. This would allow the researcher to open a web browser and move the browser onto a monitor visible by the subject in the scanner. One convenient toolbox for doing this is jsPsych. We have integrated jsPsych into our project and provide a demo using the DecNef style colored circle feedback.

## **Using jsPsych**
The source code components of jsPsych live in the `web/` directory. File `web/jsPsychFeedback.html` is the main file that will be edited to adjust the type of feedback displayed. The creating a new `draw` method different types of feedback can be created.

### **Running the Demo**<br>
1. The projectServer must be started with --remoteSubject options enabled to allow the feedback webpage to connect and receive results from the projectServer.
    - <code>conda activate rtcloud</code>
    - <code>bash ./scripts/run-projectInterface.sh --test -p sample --subjectRemote</code>

2. Connect a web browser to the main page
    - http://localhost:8888/
    - Enter 'test' for both the usnername and password since we are running it in unsecure test mode.

3. Connect a web browser to the jsPsych feedback page
    - http://localhost:8888/jspsych

4. Click the 'Run' button on the main page and view the subject feedback shown on the jsPsych page