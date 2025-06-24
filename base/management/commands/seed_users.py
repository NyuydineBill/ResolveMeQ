from django.contrib.auth import get_user_model
from django.core.management import BaseCommand
from django_seed import Seed

User = get_user_model()


class Command(BaseCommand):
    help = 'Seeds users'
    def add_arguments(self, parser):
        parser.add_argument('--number', type=int, help='Number of users to create')

    def handle(self, *args, **options):
        number = options['number']
        seeder = Seed.seeder()
        seeder.add_entity(User, number, {
            "is_active": False,
            "is_superuser": False,
            "is_staff": False,
            "is_super_admin":False,
            "is_shop_admin": False,
            "is_warehouse_admin": False,
        })
        seeder.execute()
        self.stdout.write(self.style.SUCCESS('Successfully created users'))