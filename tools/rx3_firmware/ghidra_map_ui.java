// Map references to the native RX3 Performance UI object descriptors.
// @category RX3

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;
import java.util.LinkedHashSet;
import java.util.Set;

public class ghidra_map_ui extends GhidraScript {
    @Override
    public void run() throws Exception {
        DecompInterface decompiler = new DecompInterface();
        decompiler.openProgram(currentProgram);
        String[] targets = getScriptArgs();
        Set<Function> functions = new LinkedHashSet<>();

        for (String target : targets) {
            Address address = toAddr(Long.decode(target));
            println("\n=== DATA " + target + " " + getSymbolAt(address) + " ===");
            ReferenceIterator references = currentProgram.getReferenceManager()
                .getReferencesTo(address);
            while (references.hasNext()) {
                Reference reference = references.next();
                Function function = getFunctionContaining(reference.getFromAddress());
                println(reference.getFromAddress() + " " + reference.getReferenceType() +
                    " " + (function == null ? "<no function>" : function.getName(true)));
                if (function != null) functions.add(function);
            }
        }

        for (Function function : functions) {
            println("\n=== FUNCTION " + function.getName(true) + " @ " +
                function.getEntryPoint() + " ===");
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
