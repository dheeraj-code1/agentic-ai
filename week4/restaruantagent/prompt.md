i am building restaurant order management ai system using langgraph.

I will explain you about project architecture and i also explain about the state, node and edges.


The rough plan is:

user will give its order to llm and llm will extract the dish name and quantity. Now for simplicity, we have limit it to 1 order only. If user send something that is not related to order or restaruant it will end the program. 

Now llm will call order_confirm node which need dish name and quantity.

it will handle 3 case:

based on menu, if given order is not avaiable (not in menu or quantity is 0) then llm will ask again the user to order something else, 
if order is partially available then it will ask should i proceed or you want to order somethingelse. 
if order is avaivailbe

it will put the status in state(i will explain the langgraph state later)

once llm received this it will call another node named cook if order status is confirmed

order retry is limited to 3, after 3 attemps user is not satisfied then come to end node.

when cook node is callled there are two case:

either cook is successfully cooked the dish 
or cook failed while cooking (use proability function for success and fail) give 40%c changes of fail and 60% for success

if cook failed then cook i have only 1 more attempt if still cook failed then llm should apologies to user and come to end node

if cook is succeds, then come to next node called server:
similary to cook it has also 2 retry attempts

if it fails two times then it comes to end node and give apologiy to user 

if the serve succed, status should beacome complete, should give user a message 

if serve failed then serve should called ccook again note that if cook has attempts to cook then ok otherwise llm should apologies to user


now the state of langgraph

there should be annotated message bw llm and user
there should be order details 
dish name as str
quantity as int 
available quantity as int

oder_confirm will update the available quantity by read menu
the llm should get to know order confirm status by reading the state
if a dish is not available then available quantity should be 0

then node  should update status as specified in above rules 

oder retrt attempts which are 3 
cook rery attempts which are 2
serve retry attempts which are 2 

if any failure then retry attempts should be decreaed 

if any counter is 0 then llm should apologies 
in the end there should be final result whether order complterd or not 


write code and ask if there are any open question from your side 
i will give some test cases later


MODEL = "openai/gpt-oss-20b"
