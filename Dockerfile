FROM python
RUN pip install pdm
COPY pyproject.toml pdm.lock /project/
COPY . /project/
WORKDIR /project
RUN pdm install --check --prod --no-editable
