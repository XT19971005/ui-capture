from django.core.management.base import BaseCommand
from shijie.pipeline.worker import work


class Command(BaseCommand):
    help = '执行持久队列；单个数据卷仅允许一个 Worker'

    def add_arguments(self, parser):
        parser.add_argument('--once', action='store_true')

    def handle(self, *args, **options):
        try:
            work(options['once'])
        except KeyboardInterrupt:
            pass
