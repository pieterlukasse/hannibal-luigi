import logging
import datetime
import os
import luigi
import json
import uuid
from luigi.contrib.docker_runner import DockerTask
from luigi.contrib.esindex import ElasticsearchTarget
logger = logging.getLogger('luigi-interface')
from docker import APIClient


class MrTargetTask(DockerTask):
    '''
    Subclass the DockerTask in the Luigi Docker Runner we contributed to. This
    class:
        - points to ES as a backend
        - uses our mrtarget (ex data_pipeline) containers to run jobs.
        - relies on the local /tmp folder to store data for each docker run
    '''
    run_options = luigi.Parameter(default='-h')
    mrtargetbranch = luigi.Parameter(default='master')
    mrtargetrepo = luigi.Parameter(default="quay.io/cttv/data_pipeline", significant=False)
    date = luigi.DateParameter(default=datetime.date.today(),significant=False)
    data_version = luigi.Parameter(default=datetime.date.today().strftime("hannibal-%y.%m"))

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

    auto_remove = True
    force_pull = False
    mount_tmp = False

    @property
    def container_options(self):
        opts = self._client.create_networking_config({'esnet': self._client.create_endpoint_config()})
        print opts
        return {'networking_config':opts}

    @property
    def binds(self):
        logfile = '/hannibal/logs/mrtarget_' + self.run_options[0].strip('-') + '.log'
        # datadir = '/hannibal/data'
        
        # if not os.path.exists(datadir):
        #     os.makedirs(datadir)

        with open(os.path.expanduser(logfile), 'a'):
            os.utime(os.path.expanduser(logfile), None)
    
        return [os.path.expanduser(logfile) + ':/usr/src/app/output.log']
    
    @property
    def environment(self):
        ''' pass the environment variables required by the container
        '''
        return {
            "ELASTICSEARCH_NODES": "http://" + \
				  self.eshost + ":" + \
				  self.esport,
            "CTTV_DUMP_FOLDER":"/tmp/data",
            "CTTV_DATA_VERSION": self.data_version
            
           }

    @property
    def name(self):
        return '-'.join(['mrT', self.mrtargetbranch, 
                         self.run_options[0].lstrip('-'),
                         str(uuid.uuid4().hex[:8])])

    @property
    def image(self):
        '''
        pick the container from our GCR repository
        '''
        return ':'.join([self.mrtargetrepo, self.mrtargetbranch])


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
            #http_auth=self.esauth,
            index=self.marker_index,
            doc_type=self.marker_doc_type,
            update_id=self.task_id
	    #extra_elasticsearch_args={'use_ssl':True,'verify_certs':True}
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

class MousePheno(MrTargetTask):
    run_options = ['--mp']

class GeneData(MrTargetTask):
    run_options = ['--gen']
    def requires(self):
        return UniProt(), Ensembl(), Expression(), Reactome(), MousePheno()

class EFO(MrTargetTask):
    run_options = ['--efo']

class ECO(MrTargetTask):
    run_options = ['--eco']

class Validate(MrTargetTask):
    '''
    Run the validation step, which takes the JSON submitted by each provider
    and makes sure they adhere to our JSON schema.
    Expects a list such as ['urlA','urlB'...]
    '''
    urls = luigi.Parameter()
    run_options = ['--val']

    def requires(self):
        return GeneData(), Reactome(), EFO(), ECO()

    @property
    def command(self):
        return ' '.join(['mrtarget', '--val', '--input-file', self.urls])



class EvidenceObjects(MrTargetTask):
    '''
    Dummy task that triggers execution of all validate tasks
    Specify here the list of evidence
    Recreate evidence objects (JSON representations of each validated piece of evidence)
    and store them in the backend.
    '''
    uris = json.loads(luigi.configuration.get_config().get('evidences',
                                                           't2d_evidence_sources', '[]'))

    def requires(self):
        return Validate(urls=','.join(self.uris))

    run_options = ['--evs']


class InjectedEvidence(MrTargetTask):
    '''not required by the association step, but required by the release
    '''
    def requires(self):
        return EvidenceObjects()

    run_options = ['--evs', '--inject_literature']


class AssociationObjects(MrTargetTask):
    '''the famous ass method'''
    def requires(self):
        return EvidenceObjects()

    run_options = ['--as']


class SearchObjects(MrTargetTask):
    
    def requires(self):
        return AssociationObjects(), GeneData(), EFO()

    run_options = ['--sea']


class Relations(MrTargetTask):

    def requires(self):
        return AssociationObjects()

    run_options = ['--ddr']


class DataRelease(luigi.WrapperTask):
    def requires(self):
        yield SearchObjects()
        yield InjectedEvidence()
        yield AssociationObjects()
        yield Relations()


class DataDump(MrTargetTask):
    '''when the API is deployed we can create the API dumps'''
    def requires(self):
        return DataRelease()

    run_options = ['--dump']


def main():
    luigi.run(["DryRun"])

if __name__ == '__main__':
    main()
