from django.core.management.base import BaseCommand, CommandError

from mappings.services import H3CNatSyncError, sync_h3c_nat_mappings


class Command(BaseCommand):
    help = "Sync nat_mappings data from H3C firewall via telnet."

    def add_arguments(self, parser):
        parser.add_argument("--host", type=str, default=None)
        parser.add_argument("--port", type=int, default=None)
        parser.add_argument("--username", type=str, default=None)
        parser.add_argument("--password", type=str, default=None)
        parser.add_argument(
            "--interfaces",
            type=str,
            default=None,
            help="Comma-separated interface list, e.g. GigabitEthernet0/1,GigabitEthernet0/2",
        )
        parser.add_argument("--timeout", type=int, default=None)

    def handle(self, *args, **options):
        interfaces = None
        if options["interfaces"]:
            interfaces = [item.strip() for item in options["interfaces"].split(",") if item.strip()]

        try:
            result = sync_h3c_nat_mappings(
                host=options["host"],
                port=options["port"],
                username=options["username"],
                password=options["password"],
                interfaces=interfaces,
                timeout=options["timeout"],
            )
        except H3CNatSyncError as exc:
            raise CommandError(str(exc)) from exc

        counts = result.get("interface_counts", {})
        detail = ", ".join([f"{iface}:{counts.get(iface, 0)}" for iface in result.get("interfaces", [])])
        parse_meta = result.get("parse_meta", {}) or {}
        skipped_non_int = parse_meta.get("skipped_non_int_port_total", 0)
        blocks_total = parse_meta.get("blocks_total", 0)
        self.stdout.write(
            self.style.SUCCESS(
                f"H3C NAT sync completed. rows={result['total']} interfaces={','.join(result['interfaces'])} ({detail}) blocks={blocks_total} skipped_non_int_port={skipped_non_int}"
            )
        )
