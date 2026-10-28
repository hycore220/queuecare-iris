ARG IRIS_IMAGE=iris-community:2026.3.0AI.154.0
FROM ${IRIS_IMAGE}
WORKDIR /home/irisowner/queuecare
COPY --chown=irisowner:irisowner . /home/irisowner/queuecare/
ENV PYTHONPATH=/home/irisowner/queuecare/python
RUN iris start IRIS && \
    iris merge IRIS /home/irisowner/queuecare/merge.cpf && \
    iris session IRIS < /home/irisowner/queuecare/iris.script && \
    test -f /tmp/queuecare-build.ok && \
    iris stop IRIS quietly
