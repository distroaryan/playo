import os
from django.test.runner import DiscoverRunner
from django.conf import settings
from testcontainers.postgres import PostgresContainer

class TestContainersRunner(DiscoverRunner):
    def setup_databases(self, **kwargs):
        self.postgres = PostgresContainer("postgres:15")
        self.postgres.start()
        
        # Override the database settings to use the testcontainer
        settings.DATABASES['default'].update({
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': self.postgres.dbname,
            'USER': self.postgres.username,
            'PASSWORD': self.postgres.password,
            'HOST': self.postgres.get_container_host_ip(),
            'PORT': self.postgres.get_exposed_port(5432),
        })
        
        print(f"Started Postgres Testcontainer at {settings.DATABASES['default']['HOST']}:{settings.DATABASES['default']['PORT']}")
        return super().setup_databases(**kwargs)

    def teardown_databases(self, old_config, **kwargs):
        super().teardown_databases(old_config, **kwargs)
        self.postgres.stop()
        print("Stopped Postgres Testcontainer")
