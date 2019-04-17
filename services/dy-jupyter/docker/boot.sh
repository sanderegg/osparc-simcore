#!/bin/bash

if test "${CREATE_DUMMY_TABLE}" = "1"
then
    pip install -r /home/jovyan/devel/requirements.txt
    pushd /home/jovyan/packages/simcore-sdk; pip install -r requirements-dev.txt; popd

    echo "Creating dummy tables ... using ${USE_CASE_CONFIG_FILE}"
    result="$(python scripts/dy_services_helpers/platform_initialiser_csv_files.py ${USE_CASE_CONFIG_FILE} ${INIT_OPTIONS})"
    echo "Received result of $result";
    IFS=, read -a array <<< "$result";
    echo "Received result pipeline id of ${array[0]}";
    echo "Received result node uuid of ${array[1]}";
    # the fake SIMCORE_NODE_UUID is exported to be available to the service
    export SIMCORE_PIPELINE_ID="${array[0]}";
    export SIMCORE_NODE_UUID="${array[1]}";
fi

jupyter trust ${NOTEBOOK_URL}
start-notebook.sh \
    --NotebookApp.base_url=${SIMCORE_NODE_BASEPATH} \
    --NotebookApp.extra_static_paths="['${SIMCORE_NODE_BASEPATH}/static']" \
    --NotebookApp.notebook_dir='/home/jovyan/notebooks' \
    --NotebookApp.token=""  \
    --NotebookApp.disable_check_xsrf='True' \
    --NotebookApp.quit_button='False' \
    --NotebookApp.webbrowser_open_new='0' \
    --NotebookApp.nbserver_extensions="{'input_retriever':True, 'state_handler':True}"
    # --NotebookApp.default_url=/notebooks/${NOTEBOOK_URL} #uncomment this to start the notebook right away in that notebook
    # --NotebookApp.token=""  \ this is BAD, maybe should be set to simcore
    # --NotebookApp.disable_check_xsrf='True' \ this is very BAD, but prevent POSTing when token is ''
