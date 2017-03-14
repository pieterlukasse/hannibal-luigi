import unittest
import logging
import datetime
import os
import luigi
from luigi.contrib.docker_runner import DockerTask
from luigi.contrib.esindex import ElasticsearchTarget

from os.path import expanduser
homedir = expanduser("~")

logger = logging.getLogger('luigi-interface')

BRANCH = "latest"

class OpenTargETLTask(DockerTask):

    # find which ES to point to. For now we save the status and the data
    # in the same cluster
    eshost = luigi.configuration.get_config().get('elasticsearch',
                                                        'eshost', '127.0.0.1')
    esport = luigi.configuration.get_config().get('elasticsearch',
                                                 'esport', '9200')
    
    # read from the config file how to call the marker index, where
    # to store the status of each task.
    marker_index = luigi.configuration.get_config().get('elasticsearch',
                                                        'marker-index', 'update_log')
    marker_doc_type = luigi.configuration.get_config().get('elasticsearch',
                                                           'marker-doc-type', 'entry')

    image = ':'.join(["eu.gcr.io/open-targets/data_pipeline", BRANCH])
    volumes=[os.getcwd() + '/data:/tmp/data']
    network_mode='host'
    environment = {
        "ELASTICSEARCH_HOST": eshost,
        "ELASTICSEARCH_PORT": esport,
        "CTTV_DUMP_FOLDER":"/tmp/data",
        "CTTV_DATA_VERSION":"test-17.02"
    }

    run_options = luigi.Parameter(default='-h')

    @property
    def command(self):
        return ['python','run.py',run_options]

    def output(self):
        """
        Returns a ElasticsearchTarget representing the inserted dataset.
        """
        return ElasticsearchTarget(
            host=self.eshost,
            port=self.esport,
            index=self.marker_index,
            doc_type=self.marker_doc_type,
            update_id=self.task_id
            )



    def run(self):
        '''
        extend run() of docker runner base class to touch a DB-based target.
        Opted not to extend the base class, since a docker runner job
        may prefer to create a local target, which does not implement a touch()
        method.
        '''
        DockerTask.run(self)
        self.output().touch()




class EFOdata(OpenTargETLTask):
    auto_remove= False
    
    
        


class GeneData(OpenTargETLTask):
    pass

class Validate(OpenTargETLTask):
    '''
    Run the validation step, which takes the JSON submitted by each provider
    and makes sure they adhere to our JSON schema
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