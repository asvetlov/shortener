FROM python:3.10.5-buster as installer

ENV PATH=/root/.local/bin:$PATH

# Copy to tmp folder to don't pollute home dir
RUN mkdir -p /tmp/dist
COPY dist /tmp/dist

RUN ls /tmp/dist
RUN pip install --user --find-links /tmp/dist shortener-test

FROM python:3.10.5-buster as service

LABEL org.opencontainers.image.source = "https://github.com/asvetlov/shortener"

WORKDIR /app

COPY --from=installer /root/.local /root/.local

ENV PATH=/root/.local/bin:$PATH

ENV HTTP_PORT=8080
EXPOSE $HTTP_PORT

CMD python -m shortener
