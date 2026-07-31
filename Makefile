OPNSENSE_ABI?=		26.7
PLUGIN_ORIGIN?=		security/usque

all: validate

validate:
	sh ./scripts/validate.sh

prepare:
	sh ./scripts/prepare-opnsense-tree.sh

lint:
	sh ./scripts/run-opnsense-target.sh lint

style:
	sh ./scripts/run-opnsense-target.sh style

package:
	sh ./scripts/run-opnsense-target.sh package

.PHONY: all validate prepare lint style package
