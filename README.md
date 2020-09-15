## Project Setup
- Make sure you have valid aws credentials and config in `~/.aws/credentials` and `~/.aws/config`
- Have an s3 bucket handy - create your own for unit tests - call it what you want

`vagrant up`

## Add environment variables
- set USER_FILES_BUCKET to = the name of the s3 bucket you created

## Test
-  Use pytest
    - recommend using Pycharm instead of command line (you'll have an easier time setting environment variables and debugging)
    - ENDPOINT_URL="localhost:8000"
    - IS_UNIT_TEST="yes"
    - TABLE="medicaid-details-unit-test"

## Build
- use python-lambda
- working on ci/cd with codedeploy


