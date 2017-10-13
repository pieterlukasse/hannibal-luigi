# Launch MrTarget on a mission

How we run our data pipeline (mrTarget) with luigi and docker, on a google cloud machine.

![hannibal](http://s2.quickmeme.com/img/a9/a9ed842f739e930dc8e9340bafbbaeaf77994c50c74fc6a86b046b54cb9b2c59.jpg)

Automated thanks to [Luigi](https://github.com/spotify/luigi)

## How to launch the pipeline

Authenticate to google cloud (see the [quickstart guides](https://cloud.google.com/sdk/docs/quickstarts) ) and press go!:

```sh
./launch_gce.sh <container_tag>
```

The DAG that connects the pipeline steps is defined in `pipeline-dockertask.py`

You can monitor the scheduler status by forwarding port 8082, for eg:

```sh
gcloud compute ssh --ssh-flag="-L 8082:localhost:8082"  --project=open-targets-eu-dev hannibal-master-1013-1112 --zone=europe-west1-d
```

and then browse to: http://localhost:8082/static/visualiser/index.html

To debug whether the init script has worked, log in:

```sh
gcloud compute ssh <theinstancename>
### ... and once you are logged in... 
cat /var/log/daemon.log
```


### Architectural decision records (ie. why did i write it this way):

* debian because mkarmona likes it
* ES as docker because I am not going to **ever** deal with java and jvm
* ES docker [production setup](https://www.elastic.co/guide/en/elasticsearch/reference/current/docker.html#docker-cli-run-prod-mode) respected (memory locks, docker volumes, etc, etc.. ) because we want ES to be as fast as possible
* 250GB ssd for increased I/O speed
* we are not attaching a separate disk for simplicity - and also becuase then the disk gets deleted when we delete the instances down the line
* ES and pipeline on the same (BIG) machine
  * 8 cores for ES, 32 for mrTarget, 52GB ram for ES/ 200GB for mrTarget

Notice that:
We are passing the container tag at launch and the container gets pulled once at the beginning of the pipeline.

## TODO

* elasticsearch IP to point to in case you want to run without ES
* stop the instance on its own after is done
* on pre-emptible signal stop the machine and flush ES to disk
* mrTarget --val should read a .ini file with the URIs of the data
* add data version

## Use cases

- i want to have an API+ES up for 2-4 days while frontend develops
- i want to run weekly for CD` 
- i want to run the data pipeline for a release

### CI/CD weekly flow

The script should:

1. spin ES
2. run master of mrTarget
3. test with QC that we have so far
4. if it passes, take a snapshot
5. stop the worker
6. ? stop ES
7. copy the snapshot into the main dev ES where it gets labelled with the date
8. remove the previous weekly from the main ES and the previous snapshots (we don't care about weeklies)

### i rerun the data and copy to our dev ES

The script should:
1. spin ES
2. run master of mrTarget
3. take a snapshot
5. ?reindex to devES?
6. stop ES

### Release

Launch with a specific tag and save a snapshot on gs://

## Run locally

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

**note**
For any meaningful use of hannibal-luigi, you should replace `luigi.cfg` with your own version. 
ES authentication should live on a private repo or somewhere not in version control.

On a server (with port 8082 open):

```
luigid --logdir /mnt/hannibal-tmp/log
```

should show you the screenshot of the visualizer.

### Developing

#### Editing the tasks on the VM

It can be quite useful to edit the Luigi task directly on the remote machine executing. An easy way is to install SSHFS on your laptop, which on macOs is done with `brew install sshfs`.

SSHFS reads from the ~/.ssh/config file, so create one using `gcloud compute config-ssh` as [explained](https://cloud.google.com/sdk/gcloud/reference/compute/config-ssh)

Then try to connect

```sh
sshfs -o auto_cache,reconnect,defer_permissions,noappledouble,negative_vncache,volname=hannibal 

sudo mkdir /mnt/gce
sudo chown <user> /mnt/gce

sshfs -o auto_cache,reconnect,defer_permissions,noappledouble,negative_vncache,IdentityFile=~/.ssh/google_compute_engine.pub <user_name>@<instance-name>.<region>.<project_id>:/home/<user_name> /mnt/gce

```

#### Docker login auth on google

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