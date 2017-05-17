## ETL workflow at open Targets

![hannibal](http://s2.quickmeme.com/img/a9/a9ed842f739e930dc8e9340bafbbaeaf77994c50c74fc6a86b046b54cb9b2c59.jpg)



automated thanks to [Luigi](https://github.com/spotify/luigi)



### Install
```shell
virtualenv -p python3 venv
source venv/bin/activate
pip install -r requirements.txt
```

### Usage
Locally:
```shell
# run the luigi task
# PYTHONPATH is required as luigi only uses modules in the global path
$ PYTHONPATH=. luigi --local-scheduler --module data_pipeline validation
# use --LoadPokemonTask-csv-file to load a specific dataset
$ PYTHONPATH=. luigi --local-scheduler --module data_pipeline validation \
    validation --LoadValidationTask-csv-file another.csv
```

On a server (with port 8082 open):
```
luigid --logdir /mnt/hannibal-tmp/log
```
should show you the screenshot of the visualizer.

### Docker login auth on google
The following was necessary to get docker to login without prepending `gcloud`
in front of the command
```sh
$ METADATA=http://metadata.google.internal/computeMetadata/v1
$ SVC_ACCT=$METADATA/instance/service-accounts/default
$ ACCESS_TOKEN=$(curl -H 'Metadata-Flavor: Google' $SVC_ACCT/token \
    | cut -d'"' -f 4)
$ docker login -u _token -p $ACCESS_TOKEN https://gcr.io
$ docker run --rm gcr.io/<your-project>/<your-image> <command>
```
