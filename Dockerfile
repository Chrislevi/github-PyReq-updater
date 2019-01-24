FROM ubuntu:xenial-20181218
RUN apt-get update \
  && apt-get install -y locales python3-pip python3-dev \
  && cd /usr/local/bin \
  && ln -s /usr/bin/python3 python

COPY . /WORKDIR/
WORKDIR /WORKDIR

ENV LC_ALL=en_US.UTF-8
ENV LANG=en_US.UTF-8
RUN locale-gen en_US.UTF-8


RUN pip3 install -U pip -r requirements.txt

ENTRYPOINT ["python", "pyreq.py"]
