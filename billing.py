from google.oauth2 import service_account
from google.cloud import billing_budgets_v1beta1
import datetime

# Set the path to the JSON key file for your service account
key_path = '/path/to/key.json'

# Create a credentials object using the JSON key file
credentials = service_account.Credentials.from_service_account_file(key_path)

# Create a client for the billing budgets API
client = billing_budgets_v1beta1.BudgetServiceClient(credentials=credentials)

# Set the billing account ID
billing_account_id = 'your_billing_account_id'

# Set the start and end dates for the query
start_date = datetime.datetime.today().replace(day=1).strftime('%Y-%m-%d')
end_date = datetime.datetime.today().strftime('%Y-%m-%d')

# Create a filter for the query
filter_str = f'budget_filter.credit_types_treatment = "INCLUDE_ALL_CREDITS" AND budget_filter.projects.project_id = "your_project_id" AND budget_filter.projects.credit_types.credit_type = "video_transcoding" AND budget_filter.services.service_id = "transcoder.googleapis.com" AND budget_filter.subaccounts.subaccount_id = "your_subaccount_id"'

# Create the request object
request = billing_budgets_v1beta1.ListBudgetsRequest(
    parent=f'billingAccounts/{billing_account_id}',
    time_range=billing_budgets_v1beta1.ListBudgetsRequest.TimeRange(start_time=start_date, end_time=end_date),
    filter=filter_str
)

# Send the request and get the response
response = client.list_budgets(request)

# Parse the response to get the total amount of video transcoding minutes used this month
total_minutes = 0
for budget in response:
    if budget.amount.specified_amount.units == 'min':
        total_minutes += budget.amount.specified_amount.nanos / 1000000000 / 60

print(f'Total video transcoding minutes used this month: {total_minutes}')
