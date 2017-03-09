import unittest
import logging
import datetime
import luigi
from luigi.contrib.docker_runner import DockerTask

from os.path import expanduser
homedir = expanduser("~")

logger = logging.getLogger('luigi-interface')

BRANCH = "latest"

class OpenTargETLTask(DockerTask):
    image = ':'.join(["eu.gcr.io/open-targets/data_pipeline", BRANCH])
    environment = {
        "ELASTICSEARCH_HOST":"127.0.0.1",
        "ELASTICSEARCH_PORT":"9200",
        "CTTV_DUMP_FOLDER":"/tmp/data",
        "CTTV_DATA_VERSION":"test-17.02"
    }


class HelpOptions(OpenTargETLTask):
    '''
    Just print an help message. Useful step only to figure out if anything is wrong with the container.
    TODO move to tests
    '''
    command = ['python', 'run.py', '--do-nothing']
    volumes=['/Users/epapa/ot/OpenTargETL/opentargets-luigi-test.txt:/usr/src/app/output.log']
        
    
    def output(self):
        return luigi.LocalTarget("/Users/epapa/ot/OpenTargETL/opentargets-luigi-test.txt")


class LoadBaseData(OpenTargETLTask):
    '''
    Load the base data from each main source
    '''

    command = ['python', 'run.py', '--uni']
    
    def requires(self):
        return []
 
    def output(self):
        return luigi.LocalTarget("test-uni.txt")


class Validate(OpenTargETLTask):
    '''
    Run the validation step, which takes the JSON submitted by each provider and makes sure they adhere to our JSON schema
    '''

    command = ['python', 'run.py', '--val', '--remote-file','https://storage.googleapis.com/opentargets-data-sources/16.12/cttv001_gene2phenotype-29-07-2016.json.gz']

    
    def requires(self):
        return []
 
    def output(self):
        return luigi.LocalTarget("test-val.txt")


class EvidenceObjectCreation(OpenTargETLTask):
    """
    Recreate evidence objects (JSON representations of each validated piece of evidence) and store them in the backend. 
    
    TODO: run.py scope can be limited to a few objects. describe how and implement
    """
    command = ['python', 'run.py', '--evi']

class AssociationObjectCreation(OpenTargETLTask):
    pass

class AllPipeline(luigi.WrapperTask):
    date = luigi.DateParameter(default=datetime.date.today())
    def requires(self):
        yield LoadBaseData(self.date)
        yield Validate(self.date)
        yield EvidenceObjectCreation(self.date)
        yield AssociationObjectCreation(self.date)

def main():
    luigi.run(["HelpOptions","--local-scheduler"])

if __name__ == '__main__':
    main()