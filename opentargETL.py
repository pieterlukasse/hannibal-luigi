import logging
import datetime
import os
import luigi
from luigi.contrib.docker_runner import DockerTask
from luigi.contrib.esindex import ElasticsearchTarget
import random

logger = logging.getLogger('luigi-interface')


class OpenTargETLTask(DockerTask):
    '''
    Subclass the DockerTask in the Luigi Docker Runner we contributed to. This
    class:
        - points to ES as a backend
        - uses our mrtarget (ex data_pipeline) containers to run jobs.
        - relies on the local /tmp folder to store data for each docker run
    '''
    run_options = luigi.Parameter(default='-h')
    datapipeline_branch = luigi.Parameter(default='master')
    date = luigi.DateParameter(default=datetime.date.today())



    # find which ES to point to. NOTE: this is only for the Luigi marker/status.
    # For now we save the status and the data in the same cluster. BUT the
    # pipeline actually operates on the cluster specified in the db.ini file.
    # NOTE #2: we are going to save to ES for status because this eliminates the
    # requirement for a local FS and does not introduce a dependency on S3,
    # which one of our pharma partner may not be ready to take on
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

    volumes=[os.getcwd() + '/data:/tmp/data']
    network_mode='host'

    @property
    def environment(self):
        ''' pass the environment variables required by the container
        '''
        return {
            "ELASTICSEARCH_HOST": self.eshost,
            "ELASTICSEARCH_PORT": self.esport,
            "CTTV_DUMP_FOLDER":"/tmp/data",
            "CTTV_DATA_VERSION": self.date.strftime('%y.%m.wk%W')
            }

    @property
    def name(self):
        return 'mrtarget' + self.run_options[0] + str(random.randint(1,10))

    @property
    def image(self):
        '''
        pick the container from our GCR repository
        '''
        # return ':'.join(["eu.gcr.io/open-targets/data_pipeline", self.datapipeline_branch])
        return 'alpine'

    

    @property
    def command(self):
        # return ['python', 'run.py', self.run_options]
        return '/bin/sh -c "echo "hello"; sleep 10; echo "hello again""'


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


class UniProt(OpenTargETLTask):
    run_options = ['--uni']

class GeneData(OpenTargETLTask):
    def requires(self):
        return [OpenTargETLTask(run_options=opt) for opt in ['--uni','--ens','--hpa','--rea']]

    run_options = ['--gen']


class Validate(OpenTargETLTask):
    '''
    Run the validation step, which takes the JSON submitted by each provider
    and makes sure they adhere to our JSON schema
    '''
    url = luigi.Parameter()

    def requires(self):
        return [OpenTargETLTask(run_options=opt) for opt in ['--gen','--rea','--efo','--eco']]

    run_options = ['--val', '--remote-file', url]


class ValidateAll(luigi.WrapperTask):
    ''' 
    Dummy task that triggers execution of all validate tasks
    Specify here the list of evidence
    '''
    t2d_evidence_sources = [
        'https://storage.googleapis.com/otar001-core/cttv001_gene2phenotype-15-02-2017.json.gz',
        'https://storage.googleapis.com/otar001-core/cttv001_intogen-15-02-2017.json.gz',
        'https://storage.googleapis.com/otar001-core/cttv001_phenodigm-15-02-2017.json.gz',
        'https://storage.googleapis.com/otar006-reactome/cttv006-21-02-2017.json.gz',
        'https://storage.googleapis.com/otar007-cosmic/cttv007-17-02-2017.json.gz',
    ]

    def requires(self):
        for url in t2d_evidence_sources:
            yield Validate(url=url)




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
    luigi.run(["UniProt","--local-scheduler"])

if __name__ == '__main__':
    main()