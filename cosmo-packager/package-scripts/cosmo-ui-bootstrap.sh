#!/usr/bin/env bash

function state_error
{
	echo "ERROR: ${1:-UNKNOWN} (status $?)" 1>&2
	exit 1
}

function check_pkg
{
	echo "checking to see if package $1 is installed..."
	dpkg -s $1 || state_error "package $1 is not installed"
	echo "package $1 is installed"
}

function check_user
{
	echo "checking to see if user $1 exists..."
	id -u $1 || state_error "user $1 doesn't exists"
	echo "user $1 exists"
}

function check_port
{
	echo "checking to see if port $1 is opened..."
	nc -z $1 $2 || state_error "port $2 is closed"
	echo "port $2 on $1 is opened"
}

function check_dir
{
	echo "checking to see if dir $1 exists..."
	if [ -d $1 ]; then
		echo "dir $1 exists"
	else
		state_error "dir $1 doesn't exist"
	fi
}

function check_file
{
	echo "checking to see if file $1 exists..."
	if [ -f $1 ]; then
		echo "file $1 exists"
		# if [ -$2 $1 ]; then
			# echo "$1 exists and contains the right attribs"
		# else
			# state_error "$1 exists but does not contain the right attribs"
		# fi
	else
		state_error "file $1 doesn't exists"
	fi
}

function check_upstart
{
	echo "checking to see if $1 daemon is running..."
	sudo status $1 || state_error "daemon $1 is not running"
	echo "daemon $1 is running"
}

function check_service
{
    echo "checking to see if $1 service is running..."
    sudo service $1 status || state_error "service $1 is not running"
    echo "service $1 is running"
}


PKG_NAME="cosmo-ui"
PKG_DIR="/packages/cosmo-ui"
BOOTSTRAP_LOG="/var/log/cloudify3-bootstrap.log"

BASE_DIR="/opt"
HOME_DIR="${BASE_DIR}/${PKG_NAME}"

LOG_DIR="/var/log/cosmo-ui"

PKG_INIT_DIR="${PKG_DIR}/config/init"
INIT_DIR="/etc/init"
INIT_FILE="cosmo-ui.conf"


echo "installing ${PKG_NAME}..."
sudo mkdir -p ${HOME_DIR}
check_dir ${HOME_DIR}

echo "moving some stuff around..."
sudo cp ${PKG_INIT_DIR}/${INIT_FILE} ${INIT_DIR}
check_file "${INIT_DIR}/${INIT_FILE}"

echo "creating log dir..."
sudo mkdir -p ${LOG_DIR}
check_dir "${LOG_DIR}"

echo "creating log file..."
sudo touch ${LOG_DIR}/${PKG_NAME}.log
check_file "${LOG_DIR}/${PKG_NAME}.log"

# echo "creating cosmo user..."
# sudo useradd --shell /usr/sbin/nologin --create-home --home-dir ${HOME_DIR} --groups adm cosmo
# check_user "cosmo"

# echo "pwning ${PKG_NAME} dir by cosmo user..."
# sudo chown cosmo:cosmo ${HOME_DIR}
# echo "pwning cosmo-ui logdir by ${PKG_NAME} user..."
# sudo chown cosmo:adm ${LOG_DIR}/

cd ${HOME_DIR}
echo "installing ${PKG_NAME} to ${PKG_DIR}"
sudo npm install -d ${PKG_DIR}/cosmo-ui*

echo "starting ${PKG_NAME}..."
sudo start cosmo-ui
check_upstart "cosmo-ui"