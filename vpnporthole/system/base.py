import sys
import subprocess

from pexpect import spawn as pe_spawn, TIMEOUT, EOF


class SystemCallsBase(object):
    _ip = None
    __docker_bin = None
    __sudo_cache = None
    __sudo_prompt = 'SUDO PASSWORD: '

    def __init__(self, tag, cb_sudo_password):
        self._tag = tag
        self.__cb_sudo = cb_sudo_password

    def container_ip(self, ip):
        self._ip = ip

    def connect(self):
        pass

    def disconnect(self):
        pass

    def add_route(self, subnet):
        pass

    def del_route(self, subnet):
        pass

    def list_routes(self):
        return []

    def del_all_routes(self, other_subnets):
        subnets = set(self.list_routes())
        subnets.update(other_subnets)
        for subnet in subnets:
            self.del_route(subnet)

    def add_domain(self, domain):
        pass

    def del_domain(self, domain):
        pass

    def list_domains(self):
        return []

    def del_all_domains(self):
        domains = self.list_domains()
        for domain in domains:
            self.del_domain(domain)

    # def _local_cmd(self, args):
    #     p = self._popen(args, stdout=subprocess.PIPE)
    #     p.wait()
    #     return p.stdout.readlines()

    @property
    def docker_bin(self):
        if self.__docker_bin:
            return self.__docker_bin
        self.__docker_bin = subprocess.check_output('which docker', shell=True).decode('utf-8').rstrip()
        return self.__docker_bin

    def docker_shell(self, container_id):
        args = [self.docker_bin, 'exec', '-it', container_id, '/bin/bash']
        p = self._popen(args)
        p.wait()

    def docker_run_expect(self, image, args):

        all_args = [self.docker_bin, 'run', '-it', '--rm', '--privileged', image]
        all_args.extend(args)

        self.__print_cmd(all_args)
        return Pexpect(self.__args_to_string(all_args))

    def __sudo(self):
        if self.__sudo_cache is None:
            out = subprocess.check_output('which sudo', shell=True)
            exe = out.decode('utf-8').strip()
            self.__sudo_cache = [exe, '-S', '-p', self.__sudo_prompt]
        return self.__sudo_cache

    def _shell(self, args):
        self.__print_cmd(args)
        if args[0] == 'sudo':
            args = self.__sudo() + args[1:]

        pe = Pexpect(self.__args_to_string(args), ignores=(self.__sudo_prompt,), stdout=False)

        pe.timeout = 10

        asked_sudo = False
        while True:
            i = pe.expect([self.__sudo_prompt, TIMEOUT, EOF])
            if i == 0:
                if asked_sudo:
                    pe.send(chr(3))
                    pe.wait()
                    sys.stderr.write('Sudo password was wrong\n')
                    exit(3)
                asked_sudo = True
                pe.sendline(self.__cb_sudo())
                continue
            break
        while len(pe.logfile.lines) and not pe.logfile.lines[0].strip():
            pe.logfile.lines = pe.logfile.lines[1:]
        return pe.logfile.lines

    def _popen(self, args, *vargs, **kwargs):
        self.__print_cmd(args)
        try:
            return subprocess.Popen(args, *vargs, **kwargs)
        except IOError as e:
            sys.stderr.write('Error running command: %s\n%s\n' % (str, e))
            raise

    def exec(self, docker_client, container_id, args):
        self.__print_cmd(args, 'exec')
        exec = docker_client.exec_create(container_id, args)
        for buf in docker_client.exec_start(exec['Id'], stream=True):
            sys.stdout.write(buf.decode('utf-8'))

    @property
    def stdout(self):
        return sys.stdout

    @property
    def stderr(self):
        return sys.stderr

    def __print_cmd(self, args, scope=None):
        if scope:
            line = ' >(%s)$ ' % scope
        else:
            line = ' >$ '
        line += self.__args_to_string(args)
        sys.stdout.write(line + '\n')

    def __args_to_string(self, args):
        def q(s):
            if not isinstance(s, str):
                s = str(s)
            if '"' in s:
                s = s.replace('"', '\\"')
            if '"' in s or ' ' in s:
                s = '"%s"' % s
                return s
            return s

        return ' '.join([q(s) for s in args])


class Pexpect(pe_spawn):
    class Out(object):
        lines = None
        ignore = 0
        _stdout = True

        def __init__(self, ignores, stdout):
            self.__ignores = ignores
            self.lines = []
            self._stdout = stdout

        def write(self, b):
            try:
                st = b.decode("utf-8", "replace")
            except UnicodeDecodeError as e:
                print("! except: UnicodeDecodeError: %s" % e)
                st = '\r\n'

            for line in st.splitlines(True):
                ignore = line.startswith(self.__ignores)
                if ignore:
                    self.ignore += 1
                elif self.ignore > 0:
                    self.ignore -= 1
                    return
                if not ignore:
                    self.lines.append(line)
                if self._stdout:
                    sys.stdout.write('%s' % line)

        def flush(self):
            sys.stdout.flush()

    def __init__(self, cmd, ignores=('Password', 'Username'), stdout=True):
        super(Pexpect, self).__init__(cmd)
        self.logfile = self.Out(ignores, stdout)

    def expect(self, pattern, **kwargs):
        pattern.insert(0, EOF)
        pattern.insert(1, TIMEOUT)

        i = super(Pexpect, self).expect(pattern, **kwargs)

        return i - 2

