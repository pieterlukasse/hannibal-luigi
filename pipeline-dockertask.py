import logging
import datetime
import os
import luigi
from luigi.contrib.docker_runner import DockerTask
from luigi.contrib.esindex import ElasticsearchTarget
import uuid

logger = logging.getLogger('luigi-interface')


class MrTargetTask(DockerTask):
    '''
    Subclass the DockerTask in the Luigi Docker Runner we contributed to. This
    class:
        - points to ES as a backend
        - uses our mrtarget (ex data_pipeline) containers to run jobs.
        - relies on the local /tmp folder to store data for each docker run
    '''
    run_options = luigi.Parameter(default='-h')
    mrtarget_branch = luigi.Parameter(default='master')
    date = luigi.DateParameter(default=datetime.date.today())


    '''As we are running multiple workers, the output must be a resource that is
       accessible by all workers, such as S3/distributedFileSys or database'''

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
    esauth = luigi.configuration.get_config().get('elasticsearch',
                                                  'esauth', None)
    # read from the config file how to call the marker index, where
    # to store the status of each task.
    marker_index = luigi.configuration.get_config().get('elasticsearch',
                                                        'marker-index', 'luigi_status_log')
    marker_doc_type = luigi.configuration.get_config().get('elasticsearch',
                                                           'marker-doc-type', 'entry')

    volumes = [os.getcwd() + '/data:/tmp/data']
    network_mode = 'host'
    auto_remove = False

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
        return '-'.join(['mrT', self.mrtarget_branch, 
                         self.run_options[0].lstrip('-'),
                         str(uuid.uuid4().hex[:8])])

    @property
    def image(self):
        '''
        pick the container from our GCR repository
        '''
        return ':'.join(["quay.io/cttv/data_pipeline", self.mrtarget_branch])


    @property
    def command(self):
        return ' '.join(['mrtarget'] + self.run_options)

    def output(self):
        """
        Returns a ElasticsearchTarget representing the inserted dataset.
        """
        return ElasticsearchTarget(
            host=self.eshost,
            port=self.esport,
            http_auth=self.esauth,
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

class DryRun(MrTargetTask):
    run_options = ['--dry-run']

class UniProt(MrTargetTask):
    run_options = ['--uni']

class Ensembl(MrTargetTask):
    run_options = ['--ens']

class Expression(MrTargetTask):
    run_options = ['--hpa']

class Reactome(MrTargetTask):
    run_options = ['--rea']

class GeneData(MrTargetTask):
    run_options = ['--gen']

    def requires(self):
        return UniProt(), Ensembl(), Expression(), Reactome()

class EFO(MrTargetTask):
    run_options = ['--efo']

class ECO(MrTargetTask):
    run_options = ['--eco']

class Validate(MrTargetTask):
    '''
    Run the validation step, which takes the JSON submitted by each provider
    and makes sure they adhere to our JSON schema
    '''
    url = luigi.Parameter()

    def requires(self):
        return GeneData(), Reactome(), EFO(), ECO()

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




class EvidenceObjectCreation(MrTargetTask):
    """
    Recreate evidence objects (JSON representations of each validated piece of evidence) and store them in the backend. 
    TODO: run.py scope can be limited to a few objects. describe how and implement
    """
    command = ['python', 'run.py', '--evi']


class AssociationObjectCreation(MrTargetTask):
    pass


class AllPipeline(luigi.WrapperTask):
    date = luigi.DateParameter(default=datetime.date.today())
    def requires(self):
        yield LoadBaseData(self.date)
        yield Validate(self.date)
        yield EvidenceObjectCreation(self.date)
        yield AssociationObjectCreation(self.date)

def main():
    luigi.run(["DryRun"])

if __name__ == '__main__':
    main()
