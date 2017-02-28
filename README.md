## ETL workflow at open Targets

automated thanks to [Luigi](https://github.com/spotify/luigi)



### Install
```shell
virtualenv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Usage
```shell
# run the luigi task
# PYTHONPATH is required as luigi only uses modules in the global path
$ PYTHONPATH=. luigi --local-scheduler --module data_pipeline validation
# use --LoadPokemonTask-csv-file to load a specific dataset
$ PYTHONPATH=. luigi --local-scheduler --module data_pipeline validation \
    validation --LoadValidationTask-csv-file another.csv
```