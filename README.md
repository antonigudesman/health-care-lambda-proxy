## Project Setup
- Make sure you have valid aws credentials in `~/.aws/credentials`
- Have an s3 bucket handy

`vagrant up`

- if the last line fails, then ssh into vagant and in the `/vagrant` directory run:
 `export PIPENV_VENV_IN_PROJECT=1 && python3 -m pipenv install --skip-lock` 

## Test
- `pipenv run pytest`

## Build
- use python-lambda


