### Data Collection

Okta Workflow 1 
* Data is sent to the API endpoint with the [Agentic Tools](https://github.com/bgkf/AI-LLM/blob/a31bf13575482fe8956f61d69311ad95ed2c2c24/Production/Agentic_Tools_Dashboard/agenticTools/Agentic%20Tools.sh) script and then saved in a table.<br>

![image](https://github.com/bgkf/AI-LLM/blob/a31bf13575482fe8956f61d69311ad95ed2c2c24/Production/Agentic_Tools_Dashboard/agenticTools/assets/workflow_1.png)
<br>

Okta Workflow 2 
* Called from the [createAgenticToolsFile](https://github.com/bgkf/AI-LLM/blob/a31bf13575482fe8956f61d69311ad95ed2c2c24/Production/Agentic_Tools_Dashboard/agenticTools/createAgenticToolsFile.sh) script. <br>
* Each row in the table is combined into a list and returned to the caller.<br>

![image](https://github.com/bgkf/AI-LLM/blob/a31bf13575482fe8956f61d69311ad95ed2c2c24/Production/Agentic_Tools_Dashboard/agenticTools/assets/workflow_2.png) <br>
<br>

Okta Workflow 3 
* The helper that appends each row to the list. <br>

![image](https://github.com/bgkf/AI-LLM/blob/a31bf13575482fe8956f61d69311ad95ed2c2c24/Production/Agentic_Tools_Dashboard/agenticTools/assets/workflow_3.png) <br>
