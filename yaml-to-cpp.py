import yaml
import argparse
import re
import subprocess
import os

re_comment_find    = re.compile(r".*#.*$")
re_comment_replace = re.compile(r"")

preamble = """
#include <stdint.h>
#include <stddef.h>
#include "tcg_global_mappings.h"

constexpr size_t xlen() {
    return 32;
}

struct XReg {
    uint32_t value;

    XReg(uint32_t value = 0) : value(value) {}

    explicit operator bool() const {
        return value != 0;
    }

    uint32_t operator[](size_t i) {
        return (value >> i) & 1;
    }

    uint32_t operator[](XReg reg) {
        return (value >> reg.value) & 1;
    }
};

struct CSRReg {
    uint32_t value;

    CSRReg(uint32_t value = 0) : value(value) {}

    explicit operator bool() const {
        return value != 0;
    }

    uint32_t operator[](size_t i) {
        return (value >> i) & 1;
    }

    XReg sw_read() {
        return XReg(value);
    }

    void sw_write(XReg &reg) {
        value = reg.value;
    }
};

XReg operator+(const XReg &a, const XReg &b) { return XReg(a.value + b.value); }
XReg operator-(const XReg &a, const XReg &b) { return XReg(a.value - b.value); }
XReg operator*(const XReg &a, const XReg &b) { return XReg(a.value * b.value); }
XReg operator/(const XReg &a, const XReg &b) { return XReg(a.value / b.value); }
XReg operator%(const XReg &a, const XReg &b) { return XReg(a.value % b.value); }
XReg operator&(const XReg &a, const XReg &b) { return XReg(a.value & b.value); }
XReg operator|(const XReg &a, const XReg &b) { return XReg(a.value | b.value); }
XReg operator>>(const XReg &a, const XReg &b) { return XReg(a.value >> b.value); }
XReg operator<<(const XReg &a, const XReg &b) { return XReg(a.value << b.value); }
XReg operator-(const XReg &a) { return XReg(-a.value); }
XReg operator~(const XReg &a) { return XReg(~a.value); }

struct XRegSet {
    XReg regs[32];

    XRegSet() {}

    XReg operator[](size_t i) {
        return regs[i];
    }

    XReg operator[](XReg reg) {
        return regs[reg.value];
    }
};

struct CSRRegSet {
    CSRReg regs[32];

    CSRRegSet() {}

    CSRReg operator[](size_t i) {
        return regs[i];
    }

    CSRReg operator[](XReg reg) {
        return regs[reg.value];
    }
};

struct CPU {

    static constexpr uint32_t mclicie0 = 0;
    static constexpr uint32_t mclicie1 = 1;
    static constexpr uint32_t mclicie2 = 2;
    static constexpr uint32_t mclicie3 = 3;
    static constexpr uint32_t mclicie4 = 4;
    static constexpr uint32_t mclicie5 = 5;
    static constexpr uint32_t mclicie6 = 6;
    static constexpr uint32_t mclicie7 = 7;
    static constexpr uint32_t mclicip0 = 8;
    static constexpr uint32_t mclicip1 = 9;
    static constexpr uint32_t mclicip2 = 10;
    static constexpr uint32_t mclicip3 = 11;
    static constexpr uint32_t mclicip4 = 12;
    static constexpr uint32_t mclicip5 = 13;
    static constexpr uint32_t mclicip6 = 14;
    static constexpr uint32_t mclicip7 = 15;
    static constexpr uint32_t mstatus  = 16;
    static constexpr uint32_t mcause   = 17;
    static constexpr uint32_t mepc     = 18;
    static constexpr uint32_t mnepc    = 19;
    static constexpr uint32_t flags    = 20;

    inline int32_t _signed(XReg reg) {
        return (int32_t) reg.value;
    }

    inline void delay(uint8_t) {
    }

    XRegSet X;
    CSRRegSet CSR;

    CPU() {}
"""

postamble = """
int main() {
  CPU cpu;
  cpu.qc32_subsat(0,1,2);
  return cpu.X[0].value;
}
"""

def main():
    parser = argparse.ArgumentParser(
        prog='yaml-to-cpp',
        description='Convert Xqciu instruction definitions from yaml to cpp'
    )
    parser.add_argument('file')
    parser.add_argument('-o', '--out')
    args = parser.parse_args()

    with open(args.out, "w") as out:
        out.write(preamble)
        for file in os.listdir(args.file):
            #if file != "qc32.subsat.yaml":
            #    continue

            with open(os.path.join(args.file, file), "r") as f:
                try:
                    y = yaml.safe_load(f)
                    for name in y:
                        vars = []
                        if 'variables' in y[name]['encoding']:
                            for v in y[name]['encoding']['variables']:
                                vars.append('uint8_t ' + v['name'])
                        imm_vars = ', '.join([str(i) for i in range(0,len(vars))])
                        out.write('\n')
                        out.write(f'__attribute__((annotate ("immediate: {imm_vars}")))\n')
                        out.write(f'__attribute__((annotate ("helper-to-tcg")))\n')
                        out.write(f"void {re.sub(r'\.', r'_', name)}({', '.join(vars)}) {{\n")
                        op = y[name]['operation()']
                        op = re.sub(r'#', r'//', op)
                        op = re.sub(r'\$signed', r'_signed', op)
                        #op = re.sub(r'1\'b1', r'0b1', op)
                        out.write(op)
                        out.write('}\n')
                except yaml.YAMLError as e:
                    print(e)
        out.write("};\n")
        out.write(postamble)

    command = ['clang-format', '-i', args.out]
    proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out, err = proc.communicate()
    if proc.wait() != 0:
        print(f"{' '.join(command)} exited with {proc.returncode}")
        print(f"stdout:\n{out}")
        print(f"stdout:\n{err}")

if __name__ == '__main__':
    main()
