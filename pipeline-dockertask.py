import logging
import datetime
import os
import luigi
import json
import uuid
from luigi.contrib.docker_runner import DockerTask
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
    mrtargetrepo = luigi.Parameter(default="eu.gcr.io/open-targets/mrtarget", significant=False)
    date = luigi.DateParameter(default=datetime.date.today(),significant=False)
    data_version = luigi.Parameter(default=datetime.date.today().strftime("hannibal-%y.%m"))

    '''As we are running multiple workers, the output must be a resource that is
       accessible by all workers, such as S3/distributedFileSys or database'''

    # find which ES to point to. 
    eshost = luigi.configuration.get_config().get('elasticsearch',
                                                  'eshost', '127.0.0.1')
    esport = luigi.configuration.get_config().get('elasticsearch',
                                                  'esport', '9200')
    esauth = luigi.configuration.get_config().get('elasticsearch',
                                                  'esauth', None)
    

    auto_remove = True
    force_pull = False
    mount_tmp = False

    @property
    def container_options(self):
        opts = self._client.create_networking_config({'esnet': self._client.create_endpoint_config()})
        logger.debug(opts)
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
        Returns a local Target representing the inserted dataset.
        """
        return luigi.LocalTarget('/hannibal/%s%s.done' % (self.name,self.data_version))



    def run(self):
        '''
        extend run() of docker runner base class to touch a DB-based target.
        Opted not to extend the base class, since a docker runner job
        may prefer to create a local target, which does not implement a touch()
        method.
        '''
        DockerTask.run(self)
        self.output().open("w").close()


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

class HumanPhenotype(MrTargetTask):
    run_options = ['--hpo']

class MammalianPhenotype(MrTargetTask):
    run_options = ['--mp']

class GeneData(MrTargetTask):
    run_options = ['--gen']
    def requires(self):
        return UniProt(), Ensembl(), Expression(), Reactome(), MammalianPhenotype()

class EFO(MrTargetTask):
    run_options = ['--efo']

class ECO(MrTargetTask):
    run_options = ['--eco']

class Validate(MrTargetTask):
    '''
    Run the validation step, which takes the JSON submitted by each provider
    and makes sure they adhere to our JSON schema.
    Uses the default list contained in the pipeline
    '''
    run_options = ['--val']
    def requires(self):
        return GeneData(), Reactome(), EFO(), ECO()


class EvidenceObjects(MrTargetTask):
    '''
    Specify here the list of evidence
    Recreate evidence objects (JSON representations of each validated piece of evidence)
    and store them in the backend.
    '''

    def requires(self):
        return Validate()

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
    mrtargetbranch = luigi.Parameter(default='master')
    mrtargetrepo = luigi.Parameter(default="eu.gcr.io/open-targets/mrtarget", significant=False)
    data_version = luigi.Parameter(default=datetime.date.today().strftime("hannibal-%y.%m"))
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
