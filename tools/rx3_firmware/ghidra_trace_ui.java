// Ghidra headless helper: decompile named RX3 UI functions and list callers.
// @category RX3

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;

public class ghidra_trace_ui extends GhidraScript {
    @Override
    public void run() throws Exception {
        DecompInterface decompiler = new DecompInterface();
        decompiler.openProgram(currentProgram);

        String[] arguments = getScriptArgs();
        boolean showCallers = true;
        int firstArgument = 0;
        if (arguments.length > 0 && arguments[0].equals("--no-callers")) {
            showCallers = false;
            firstArgument = 1;
        }
        for (int argumentIndex = firstArgument;
             argumentIndex < arguments.length; argumentIndex++) {
            String argument = arguments[argumentIndex];
            Function function = null;
            if (argument.startsWith("0x")) {
                Address address = toAddr(Long.decode(argument));
                function = getFunctionAt(address);
                if (function == null) {
                    function = getFunctionContaining(address);
                }
            } else {
                for (Function candidate : currentProgram.getFunctionManager().getFunctions(true)) {
                    if (candidate.getName().equals(argument)) {
                        function = candidate;
                        break;
                    }
                }
            }

            if (function == null) {
                println("=== NOT FOUND: " + argument + " ===");
                continue;
            }

            println("\n=== " + function.getName(true) + " @ " + function.getEntryPoint() + " ===");
            if (showCallers) {
                println("-- callers --");
                ReferenceIterator references = currentProgram.getReferenceManager()
                    .getReferencesTo(function.getEntryPoint());
                while (references.hasNext()) {
                    Reference reference = references.next();
                    Function caller = getFunctionContaining(reference.getFromAddress());
                    println(reference.getFromAddress() + "  " +
                        (caller == null ? "<no function>" : caller.getName(true)));
                }
            }

            println("-- decompile --");
            DecompileResults result = decompiler.decompileFunction(function, 90, monitor);
            if (result.decompileCompleted()) {
                println(result.getDecompiledFunction().getC());
            } else {
                println("FAILED: " + result.getErrorMessage());
            }
        }
        decompiler.dispose();
    }
}
