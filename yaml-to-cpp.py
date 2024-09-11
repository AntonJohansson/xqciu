import yaml
import argparse
import re
import subprocess
import os
import math

re_comment_find    = re.compile(r".*#.*$")
re_comment_replace = re.compile(r"")

preamble = """
#include <stdint.h>
#include <stddef.h>
#include <initializer_list>
#include <iterator>

constexpr size_t xlen() {
    return 32;
}

template<int N>
struct Bits {
    uint32_t value;
};

struct XRegRange {
  uint32_t value;
  uint32_t length;

  XRegRange(uint32_t value, uint32_t length = 1)
    : value(value), length(length) {}
};

struct __attribute__((packed)) XReg {
    uint32_t value;

    XReg(uint32_t value = 0) : value(value) {}
    XReg(std::initializer_list<XRegRange> ranges)
        : value(0) {
        size_t offset = 0;
        for (auto it = std::rbegin(ranges); it != std::rend(ranges); ++it) {
          value |= (it->value << offset);
          offset += it->length;
        }
    }

    explicit operator bool() const {
        return value != 0;
    }

    uint32_t operator[](size_t i) {
        return (value >> i) & 1;
    }

    uint32_t operator[](XReg reg) {
        return (value >> reg.value) & 1;
    }

    XRegRange range(size_t b, size_t e) {
        uint32_t mask = ((uint32_t) -1) >> (31 - e);
        return XRegRange((value & mask) >> b, e-b+1);
    }
};

struct CSRReg {
    uint32_t value;
    uint32_t NMI;
    uint32_t MIE;
    uint32_t MPIE;
    uint32_t MPP;
    uint32_t MPRV;

    CSRReg(uint32_t value = 0) : value(value) {}

    explicit operator bool() const {
        return value != 0;
    }

    uint32_t operator[](size_t i) {
        return (value >> i) & 1;
    }

    XReg address() {
        return XReg(value);
    }

    XReg sw_read() {
        return XReg(value);
    }

    void sw_write(XReg reg) {
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
XReg operator==(const XReg &a, const XReg &b) { return a.value == b.value; }

struct XRegSet {
    XReg regs[32];

    XRegSet() {}

    XReg &operator[](size_t i) {
        return regs[i];
    }

    XReg &operator[](XReg reg) {
        return regs[reg.value];
    }
};

struct CSRRegSet {
    CSRReg regs[32];

    CSRRegSet() {}

    CSRReg &operator[](size_t i) {
        return regs[i];
    }

    CSRReg &operator[](XReg reg) {
        return regs[reg.value];
    }
};

template<int N>
void write_memory(XReg va, XReg value);
template<>
void write_memory<32>(XReg va, XReg value) {
}

template<int N>
XReg read_memory(XReg va);
template<>
XReg read_memory<32>(XReg va) {
}

enum class PrivilegeMode {
    S, U, M
};

enum class ExtensionName {
    S, U
};

void set_mode(const PrivilegeMode m) {
}

bool implemented(const ExtensionName n) {
    return true;
}

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
    static constexpr uint32_t mncause  = 18;
    static constexpr uint32_t mepc     = 19;
    static constexpr uint32_t mnepc    = 20;
    static constexpr uint32_t flags    = 21;

    static constexpr uint32_t XLEN     = 32;

    inline int32_t _signed(XReg reg) {
        return (int32_t) reg.value;
    }

    inline void delay(uint8_t) {
    }

    XRegSet X;
    CSRRegSet CSR;

#define PC X[0]

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
    parser.add_argument('--output-decode')
    args = parser.parse_args()

    if args.output_decode:
        with open(args.output_decode, "w") as out:
            defs = {}
            formats = []
            for file in os.listdir(args.file):
                #if file != "qc32.compress2.yaml":
                #    continue

                with open(os.path.join(args.file, file), "r") as f:
                    try:
                        y = yaml.safe_load(f)
                        for name in y:
                            vars = []
                            pattern = y[name]['encoding']['match']
                            pattern = re.sub(r'([-]+)', r' \1 ', pattern)
                            pattern = re.sub(r'-', r'.', pattern)

                            format = f"{re.sub(r'\.', r'_', name)} {pattern}"

                            if 'variables' in y[name]['encoding']:
                                for v in y[name]['encoding']['variables']:
                                    print(name)
                                    print(v['location'])
                                    if '|' in v['location']:
                                        continue

                                    offsets = [int(s) for s in v['location'].split('-')]
                                    length = offsets[0] - offsets[1] + 1
                                    name = f"{v['name']}_{offsets[1]}_{length}"
                                    defs[name] = f"%{name} {offsets[1]}:{length}"
                                    format = format + f" {v['name']} = @{name}"
                                    #vars.append('uint8_t ' + v['name'])

                            formats.append(format)

                    except yaml.YAMLError as e:
                        print(e)
            for name in defs:
                out.write(defs[name])
                out.write('\n')
            for f in formats:
                out.write(f)
                out.write('\n')




    if args.out:
        with open(args.out, "w") as out:
            out.write(preamble)
            for file in os.listdir(args.file):
                if file != "qc32.subsat.yaml":
                    continue
                #if file != "qc16.mienter.nest.yaml":
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
                            op = re.sub(r"([0-9]+)'b([0-9]+)", r'XRegRange(0b\2, \1)', op)
                            op = re.sub(r'\[([0-9]+):([0-9]+)\]', r'.range(\2, \1)', op)
                            op = re.sub(r'implemented\?', r'implemented', op)
                            #for size,bits in re.findall(r"([0-9]+)'b([0-9]+)", op):
                            #    size_rounded = 8*math.floor((Int(size)+8-1)/8)
                            #    print(f"(uint{size}_t) 0b{bits}")
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
