# the image of test/cross/Dockerfile, named by the Dockerfile's hash
here=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
repo=$(CDPATH= cd -- "$here/../.." && pwd)
image=mink-cross:$(sha256sum "$here/Dockerfile" | cut -c1-16)
