OPNSENSE_ABI?=		26.7
PLUGIN_ORIGIN?=		security/usque
PORT_ORIGIN?=		security/usque-nativetun

all: validate

validate:
	sh ./scripts/validate.sh

prepare:
	sh ./scripts/prepare-opnsense-tree.sh

ports-prepare:
	sh ./scripts/prepare-ports-tree.sh

port-check:
	sh ./scripts/run-freebsd-port-target.sh check

port-package:
	sh ./scripts/run-freebsd-port-target.sh package

port-clean:
	sh ./scripts/run-freebsd-port-target.sh clean

lint:
	sh ./scripts/run-opnsense-target.sh lint

style:
	sh ./scripts/run-opnsense-target.sh style

package:
	sh ./scripts/run-opnsense-target.sh package

.PHONY: all validate prepare ports-prepare port-check port-package port-clean \
	lint style package
